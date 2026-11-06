#!/usr/bin/env python3
"""code-verify core — two-stage pre-commit validation (agent-neutral).

Deterministic core shared by the code-verify skill (DSH / Claude Code / future
agent backends) and the git pre-commit hook. Stage 1 (static) combines
deterministic checks with a pluggable AI review backend that executes the
adapted Anthropic official code-review workflow against pluggable review
rules. Stage 2 (target) runs the repository's own validation command — an
integration suite, a simulator, a device farm, an on-board firmware test —
inside an isolated snapshot worktree. A validation record keyed by the git
staged-tree hash gates commit permission.

State layout (inside <git-common-dir>/code-verify/, shared across worktrees):
    records/<tree40>.json   validation records (the commit gate input)
    reports/<tree12>/       reports, AI review results, logs, prompts
    work/<tree12>/          isolated snapshot worktrees
    code_verify.py          self-contained copy installed for the git hook

Target repository config: <repo-root>/.code-verify/config.json (see SKILL.md).

Exit codes: 0 ok/PASS/allowed · 1 FAIL / gate blocked · 2 ERROR / config /
infra · 3 REVIEW_REQUIRED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 2
STATUSES_STATIC = ("PASS", "FAIL", "REVIEW_REQUIRED", "ERROR")
STATUSES_TARGET = ("PASS", "FAIL", "INCONCLUSIVE", "INFRA_ERROR")
AI_BACKENDS = ("auto", "dsh", "claude-code")


class VerifyError(Exception):
    """Fatal, fail-closed error (exit 2)."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd, cwd=None, timeout=None, env=None, stdin_bytes=None):
    """Run a command; never raises on non-zero exit. Returns dict.

    On timeout the whole process tree is killed (Windows: taskkill /T — the
    direct child may be a shell wrapper; POSIX: killpg) and the pipes are
    drained with a bounded wait so orphaned grandchildren cannot hang us.
    """
    import signal  # noqa: F401 — referenced only on POSIX paths
    started = time.time()
    popen_kwargs = {}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(
            [str(c) for c in cmd],
            cwd=str(cwd) if cwd else None,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **popen_kwargs,
        )
    except OSError as exc:
        return {
            "exit_code": None, "output": "", "timed_out": False,
            "spawn_error": str(exc), "duration_sec": 0.0,
        }

    def kill_tree():
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True, timeout=15,
                )
            else:
                import signal
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    try:
        out, _ = proc.communicate(input=stdin_bytes, timeout=timeout)
        return {
            "exit_code": proc.returncode,
            "output": out.decode("utf-8", errors="replace"),
            "timed_out": False, "spawn_error": None,
            "duration_sec": round(time.time() - started, 2),
        }
    except subprocess.TimeoutExpired:
        kill_tree()
        try:
            out, _ = proc.communicate(timeout=15)
        except Exception:
            out = b""
        return {
            "exit_code": None,
            "output": out.decode("utf-8", errors="replace"),
            "timed_out": True, "spawn_error": None,
            "duration_sec": round(time.time() - started, 2),
        }


# --------------------------------------------------------------------------
# git plumbing
# --------------------------------------------------------------------------

def git(repo: Path, args, stdin_bytes=None, env_extra=None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["git"] + [str(a) for a in args],
        cwd=str(repo), env=env, input=stdin_bytes,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def git_out(repo: Path, args, stdin_bytes=None, env_extra=None) -> str:
    proc = git(repo, args, stdin_bytes=stdin_bytes, env_extra=env_extra)
    if proc.returncode != 0:
        raise VerifyError(
            f"git {' '.join(str(a) for a in args)} failed:\n"
            f"{proc.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return proc.stdout.decode("utf-8", errors="replace").strip()


def repo_root_from(start: Path) -> Path:
    proc = git(start, ["rev-parse", "--show-toplevel"])
    if proc.returncode != 0:
        raise VerifyError(
            "not inside a git repository — code-verify operates on the staged "
            "tree of the target repository"
        )
    return Path(proc.stdout.decode().strip())


def empty_tree_sha(repo: Path) -> str:
    return git_out(repo, ["mktree"], stdin_bytes=b"")


def base_head(repo: Path):
    proc = git(repo, ["rev-parse", "--verify", "-q", "HEAD"])
    if proc.returncode != 0:
        return None
    return proc.stdout.decode().strip()


def staged_tree(repo: Path) -> str:
    """Snapshot identity of the code to be committed: the staged tree hash."""
    return git_out(repo, ["write-tree"])


def changed_files(repo: Path) -> dict:
    head = base_head(repo)
    spec = [head] if head else [empty_tree_sha(repo)]
    out = git_out(repo, ["diff", "--cached", "--name-status", "--no-renames", *spec])
    files = {"A": [], "M": [], "D": []}
    for line in out.splitlines():
        if not line.strip():
            continue
        status, _, path = line.partition("\t")
        files.setdefault(status.strip()[0] or "M", []).append(path)
    return files


def state_dir(repo: Path) -> Path:
    common = git_out(repo, ["rev-parse", "--git-common-dir"])
    p = Path(common)
    if not p.is_absolute():
        p = (repo / p).resolve()
    return p / "code-verify"


def resolve_claude(bin_name: str):
    """Resolve the claude CLI across Windows/npm launchers."""
    resolved = shutil.which(bin_name) or shutil.which(bin_name + ".cmd")
    if not resolved:
        return None
    low = resolved.lower()
    if low.endswith((".cmd", ".bat")):
        return ["cmd", "/c", resolved]
    if low.endswith(".ps1"):
        cmd_sibling = resolved[:-5] + ".cmd"
        if Path(cmd_sibling).exists():
            return ["cmd", "/c", cmd_sibling]
    return [resolved]


# --------------------------------------------------------------------------
# isolation worktree
# --------------------------------------------------------------------------

def isolation_dir(repo: Path, tree: str, state: Path) -> Path:
    work = state / "work" / tree[:12]
    if work.exists():
        if not (work / ".git").is_file():
            raise VerifyError(
                f"isolation worktree {work} exists but is not a valid git "
                "worktree (crashed residue) — remove it manually with "
                "`git worktree remove --force <path>` + `git worktree prune` "
                "and re-run"
            )
        return work
    commit = git_out(
        repo, ["commit-tree", tree, "-m", "code-verify snapshot (dangling)"],
        env_extra={
            "GIT_AUTHOR_NAME": "code-verify", "GIT_AUTHOR_EMAIL": "code-verify@invalid",
            "GIT_COMMITTER_NAME": "code-verify", "GIT_COMMITTER_EMAIL": "code-verify@invalid",
        },
    )
    work.parent.mkdir(parents=True, exist_ok=True)
    git_out(repo, ["worktree", "add", "--quiet", "--detach", work, commit])
    return work


# --------------------------------------------------------------------------
# config / fingerprints
# --------------------------------------------------------------------------

def load_config(repo: Path) -> dict:
    path = repo / ".code-verify" / "config.json"
    if not path.is_file():
        raise VerifyError(
            "missing target repository config: .code-verify/config.json\n"
            "code-verify never defaults to PASS; create the config first (see "
            "SKILL.md 'Target repository setup')."
        )
    try:
        # utf-8-sig tolerates a UTF-8 BOM (PowerShell 5.1 Set-Content
        # -Encoding UTF8 and Notepad emit one); plain utf-8 would fail
        # closed with an opaque "Unexpected UTF-8 BOM" error.
        cfg = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerifyError(f"invalid .code-verify/config.json: {exc}")
    if not isinstance(cfg, dict):
        raise VerifyError(".code-verify/config.json must be a JSON object")
    return cfg


def test_config_fingerprint(repo: Path, cfg: dict) -> str:
    h = hashlib.sha256()
    for rel in cfg.get("test_config_files", []):
        p = repo / rel
        h.update(rel.encode())
        h.update(b"\0")
        h.update(sha256_file(p).encode() if p.is_file() else b"<missing>")
        h.update(b"\0")
    return h.hexdigest()


def target_config_fingerprint(target_cfg: dict) -> str:
    """Fingerprint the whole target config; any change (command, target id,
    kind, timeout, junit path) invalidates previous target PASS records."""
    payload = json.dumps(target_cfg, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def artifacts_fingerprints(repo: Path, cfg: dict) -> list:
    """Fingerprint every configured build artifact (a firmware image, a
    binary, a package...). The gate refuses commits when any artifact
    changed after target validation."""
    out = []
    for rel in cfg.get("artifacts") or []:
        p = repo / rel
        if not p.is_file():
            raise VerifyError(f"configured artifact not found: {rel}")
        out.append({"path": str(rel), "sha256": sha256_file(p)})
    return out


# --------------------------------------------------------------------------
# records / reports
# --------------------------------------------------------------------------

def record_path(state: Path, tree: str) -> Path:
    return state / "records" / f"{tree}.json"


def load_record(state: Path, tree: str):
    p = record_path(state, tree)
    if not p.is_file():
        return None
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        # keep the 0/1/2/3 exit-code contract: a corrupt record is an
        # ERROR (2), not an uncaught traceback
        raise VerifyError(f"corrupt validation record {p}: {exc}")
    if not isinstance(rec, dict) or rec.get("schema") != SCHEMA_VERSION:
        # foreign/old schema (e.g. a v1 fw-verify record): ignore it —
        # fail-closed, the tree must be re-verified with this schema
        return None
    return rec


def save_record(state: Path, rec: dict) -> Path:
    p = record_path(state, rec["tree"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def report_dir(state: Path, tree: str) -> Path:
    d = state / "reports" / tree[:12]
    d.mkdir(parents=True, exist_ok=True)
    return d


def base_record(repo: Path, tree: str) -> dict:
    return {
        "schema": SCHEMA_VERSION,
        "tree": tree,
        "base_head": base_head(repo),
        "repo_root": str(repo),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "files": changed_files(repo),
        "static": None,
        "target": None,
    }


# --------------------------------------------------------------------------
# AI review backends
# --------------------------------------------------------------------------

BUNDLED_RULES = ("generic", "firmware-board")


def load_rules(repo: Path, cfg: dict, args) -> tuple:
    """Resolve the review rules: --rules override > config `review_rules`
    (a bundled ruleset name or a repo-relative/absolute path) > bundled
    `generic`. Returns (selector, rules_text)."""
    selector = (getattr(args, "rules", None) or cfg.get("review_rules")
                or "generic")
    if re.fullmatch(r"[A-Za-z0-9_-]+", selector):
        p = (Path(__file__).resolve().parent.parent / "references" / "rules"
             / f"{selector}.md")
        if not p.is_file():
            raise VerifyError(
                f"unknown review rules {selector!r} "
                f"(bundled rulesets: {', '.join(BUNDLED_RULES)})"
            )
    else:
        p = Path(selector)
        if not p.is_absolute():
            p = repo / p
        if not p.is_file():
            raise VerifyError(
                f"review rules file not found: {selector} (resolved {p})"
            )
    return selector, p.read_text(encoding="utf-8")


def build_prompt(iso: Path, repo: Path, rules: str, context_file) -> str:
    template = (
        Path(__file__).resolve().parent.parent / "references" / "review-workflow.md"
    )
    if not template.is_file():
        raise VerifyError(
            f"review workflow template not found at {template}; pass --rules "
            "only covers rules — the skill layout is required for AI review"
        )
    prompt = template.read_text(encoding="utf-8")
    if context_file:
        context = Path(context_file).read_text(encoding="utf-8", errors="replace")
    else:
        stat = git_out(repo, ["diff", "--cached", "--stat"])
        context = (
            "The author did not provide additional intent. Staged diff stat:\n" + stat
        )
    files = "\n".join(
        f"{status}: {path}"
        for status, paths in changed_files(repo).items()
        for path in paths
    )
    prompt = prompt.replace("{{CHANGED_FILES}}", files or "(no changed files)")
    prompt = prompt.replace("{{CHANGE_CONTEXT}}", context.strip())
    prompt = prompt.replace("{{PROJECT_RULES}}", rules)
    return prompt


def iter_json_objects(text: str):
    """Yield every parseable JSON object in text, in order (skips banners)."""
    text = re.sub(r"```(?:json)?", "", text)
    i = text.find("{")
    while i >= 0:
        try:
            obj, _ = json.JSONDecoder().raw_decode(text[i:])
            if isinstance(obj, dict):
                yield obj
        except json.JSONDecodeError:
            pass
        i = text.find("{", i + 1)


def first_json(text: str):
    for obj in iter_json_objects(text):
        return obj
    return None


def extract_ai_json(text: str):
    for obj in iter_json_objects(text):
        if "verdict" in obj:
            return obj
    return None


def extract_claude_envelope(text: str):
    """The claude -p --output-format json envelope; banners may precede it."""
    for obj in iter_json_objects(text):
        if "result" in obj and ("subtype" in obj or "session_id" in obj
                                or "duration_api_ms" in obj):
            return obj
    for obj in iter_json_objects(text):
        if "result" in obj:
            return obj
    return None


def validate_ai_result(ai: dict) -> dict:
    verdict = ai.get("verdict")
    if verdict not in STATUSES_STATIC:
        raise VerifyError(f"AI result has invalid verdict: {verdict!r}")
    for key in ("findings", "risks"):
        if not isinstance(ai.get(key), list):
            raise VerifyError(f"AI result field {key!r} must be a list")
    findings = ai["findings"]
    blockers = [f for f in findings if f.get("severity") == "blocker"]
    if verdict == "PASS" and (blockers or ai["risks"]):
        verdict = "REVIEW_REQUIRED"  # defensive: verdict must match content
    return {**ai, "verdict": verdict}


def run_backend_claude(repo: Path, iso: Path, prompt: str, cfg: dict, reports: Path):
    claude = resolve_claude(cfg.get("claude_bin", "claude"))
    if not claude:
        raise VerifyError(
            "claude CLI not found on PATH (backend claude-code). Install "
            "Claude Code or run the DSH backend: static --prepare --backend dsh"
        )
    cmd = claude + [
        "-p", "--output-format", "json",
        "--disallowedTools", "Edit", "Write", "NotebookEdit",
        "WebFetch", "WebSearch",
        "--allowedTools", "Read", "Grep", "Glob", "Task", "TodoWrite",
        "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)",
        "Bash(git status:*)", "Bash(git rev-parse:*)",
    ]
    (reports / "review-prompt.md").write_text(prompt, encoding="utf-8")
    res = run(
        cmd, cwd=iso, timeout=int(cfg.get("claude_timeout_sec", 1800)),
        stdin_bytes=prompt.encode("utf-8"),
    )
    (reports / "claude-run.log").write_text(
        f"$ {' '.join(cmd)}\n\n{res['output']}", encoding="utf-8"
    )
    if res["timed_out"]:
        raise VerifyError("claude review timed out (fail-closed ERROR)")
    if res["spawn_error"]:
        raise VerifyError(f"claude spawn failed: {res['spawn_error']}")
    if res["exit_code"] != 0:
        raise VerifyError(
            f"claude exited {res['exit_code']} — AI review did not complete "
            "(fail-closed ERROR)"
        )
    envelope = extract_claude_envelope(res["output"])
    final_text = envelope.get("result", "") if envelope else res["output"]
    ai = extract_ai_json(final_text)
    if ai is None:
        (reports / "ai-review-unparseable.txt").write_text(final_text, encoding="utf-8")
        raise VerifyError("could not extract JSON verdict from claude result (fail-closed)")
    (reports / "ai-review.json").write_text(
        json.dumps(ai, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return validate_ai_result(ai)


def resolve_backend(cfg: dict, override) -> str:
    backend = override or cfg.get("ai_backend", "auto")
    if backend == "auto":
        backend = "claude-code" if resolve_claude(cfg.get("claude_bin", "claude")) else "dsh"
    if backend not in ("dsh", "claude-code"):
        raise VerifyError(f"unknown ai_backend: {backend!r} (use dsh or claude-code)")
    return backend


# --------------------------------------------------------------------------
# Stage 1: static
# --------------------------------------------------------------------------

def run_deterministic(repo: Path, iso: Path, cfg: dict, reports: Path):
    results = []
    failed = False
    for i, cmd in enumerate(cfg.get("static_commands", [])):
        log = reports / "logs" / f"static-{i}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        res = run(cmd, cwd=iso, timeout=int(cfg.get("static_timeout_sec", 900)))
        log.write_text(
            f"$ {' '.join(str(c) for c in cmd)}\nexit={res['exit_code']}\n\n"
            + res["output"],
            encoding="utf-8",
        )
        entry = {
            "command": [str(c) for c in cmd],
            "exit_code": res["exit_code"],
            "timed_out": res["timed_out"],
            "spawn_error": res["spawn_error"],
            "duration_sec": res["duration_sec"],
            "log": str(log.relative_to(state_dir(repo))),
        }
        results.append(entry)
        if res["exit_code"] != 0 or res["timed_out"] or res["spawn_error"]:
            failed = True
    return results, failed


def write_static_reports(state: Path, rec: dict) -> Path:
    reports = report_dir(state, rec["tree"])
    static = rec["static"]
    (reports / "static.json").write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    lines = [
        "# code-verify Static Review Report", "",
        f"- Snapshot (staged tree): `{rec['tree']}`",
        f"- Base HEAD: `{rec['base_head'] or '(no commits yet)'}`",
        f"- Status: **{static['status']}**",
        f"- Backend: {static['backend']}",
        f"- Timestamp: {static['timestamp']}", "",
        "## Changed files", "",
    ]
    for status, paths in rec["files"].items():
        for p in paths:
            lines.append(f"- {status} {p}")
    lines += ["", "## Deterministic checks", ""]
    if static["deterministic"]:
        for d in static["deterministic"]:
            verdict = "ok" if d["exit_code"] == 0 else "FAILED"
            lines.append(f"- [{verdict}] `{' '.join(d['command'])}` (exit {d['exit_code']}, log: {d['log']})")
    else:
        lines.append("- (none configured)")
    lines += ["", "## AI review", ""]
    ai = static.get("ai_review")
    if ai:
        lines += [
            f"- Verdict: **{ai['verdict']}** · findings {ai['findings_count']} · risks {ai['risks_count']}",
            f"- Result: `{ai['raw_result']}`", "",
            "### Findings", "",
        ]
        if ai.get("findings"):
            for f in ai["findings"]:
                lines += [
                    f"- **[{f.get('severity','?')}] {f.get('file','?')}:{f.get('line','?')}** "
                    f"({f.get('category','?')}) — {f.get('description','')}",
                    f"  - trigger: {f.get('trigger_condition','')}",
                    f"  - fix: {f.get('suggested_fix','')}",
                ]
        else:
            lines.append("- none")
        lines += ["", "### Risks (REVIEW_REQUIRED channel)", ""]
        if ai.get("risks"):
            for r in ai["risks"]:
                lines.append(
                    f"- **{r.get('file','?')}:{r.get('line','?')}** "
                    f"({r.get('reason','?')}) — {r.get('description','')} · "
                    f"check on target: {r.get('what_to_check_on_target','')}"
                )
        else:
            lines.append("- none")
    else:
        lines.append("- not run")
    out = reports / "static.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def finalize_static(repo: Path, state: Path, tree: str, cfg: dict, backend: str,
                    det_results, ai_result, rules=None, ai_error=None) -> tuple:
    rec = load_record(state, tree) or base_record(repo, tree)
    reports = report_dir(state, tree)
    if ai_error:
        status = "ERROR"
    else:
        status = ai_result["verdict"]
    rec["static"] = {
        "status": status,
        "timestamp": now_iso(),
        "backend": backend,
        "rules": rules,
        "snapshot_tree": tree,
        "isolation_dir": str(state / "work" / tree[:12]),
        "deterministic": det_results,
        "ai_review": None if ai_result is None else {
            "verdict": ai_result["verdict"],
            "findings_count": len(ai_result.get("findings", [])),
            "risks_count": len(ai_result.get("risks", [])),
            "findings": ai_result.get("findings", []),
            "risks": ai_result.get("risks", []),
            "raw_result": str(reports / "ai-review.json"),
        },
        "ai_error": ai_error,
    }
    save_record(state, rec)
    report = write_static_reports(state, rec)
    return rec, report


def pending_path(state: Path, tree: str) -> Path:
    return state / "records" / f"{tree}.pending.json"


def cmd_static(args) -> int:
    repo = repo_root_from(Path(args.repo_root))
    state = state_dir(repo)
    cfg = load_config(repo)
    tree = staged_tree(repo)

    # DSH finalize path: consume the prepared prompt's result, never re-run
    # deterministic checks (they already ran during --prepare).
    if args.ai_result:
        if args.dry_run:
            print(json.dumps({"dry_run": True, "note": "finalize needs no dry-run"}))
            return 0
        pending_file = pending_path(state, tree)
        if not pending_file.is_file():
            raise VerifyError(
                "no prepared AI review for the current staged tree; run "
                "`code_verify.py static --prepare --backend dsh` first"
            )
        pending = json.loads(pending_file.read_text(encoding="utf-8"))
        if pending["tree"] != tree:
            raise VerifyError("staged tree changed since --prepare; re-prepare")
        backend = pending["backend"]
        det_results = pending["deterministic"]
        reports = report_dir(state, tree)
        raw = Path(args.ai_result).read_text(encoding="utf-8")
        ai = extract_ai_json(raw)
        if ai is None:
            raise VerifyError(f"result file {args.ai_result} contains no JSON verdict object")
        ai = validate_ai_result(ai)
        (reports / "ai-review.json").write_text(
            json.dumps(ai, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        rec, report = finalize_static(repo, state, tree, cfg, backend,
                                      det_results, ai,
                                      rules=pending.get("rules"))
        pending_file.unlink(missing_ok=True)
        status = rec["static"]["status"]
        print(f"Static Review: {status}\nReport: {report}")
        return 0 if status == "PASS" else (3 if status == "REVIEW_REQUIRED" else 1)

    backend = resolve_backend(cfg, args.backend)

    if args.dry_run:
        plan = {
            "dry_run": True, "tree": tree, "backend": backend,
            "static_commands": cfg.get("static_commands", []),
            "note": "no isolation, no AI call, no record written",
        }
        print(json.dumps(plan, indent=2))
        return 0

    iso = isolation_dir(repo, tree, state)
    reports = report_dir(state, tree)
    det_results, det_failed = run_deterministic(repo, iso, cfg, reports)

    if det_failed:
        rec, report = finalize_static(
            repo, state, tree, cfg, backend, det_results, None,
            ai_error="skipped AI review: deterministic check failed (status FAIL)",
        )
        rec["static"]["status"] = "FAIL"
        save_record(state, rec)
        write_static_reports(state, rec)
        print(f"Static Review: FAIL (deterministic check failed; see {report})")
        return 1

    if backend == "dsh" or args.prepare:
        # Prepare-and-exit: the dsh backend always needs the agent in the
        # loop; --prepare also lets any other backend stop after writing the
        # prompt + pending record, for an agent-in-the-loop run instead of
        # the unattended CLI call.
        rules_sel, rules = load_rules(repo, cfg, args)
        prompt = build_prompt(iso, repo, rules, args.context)
        (reports / "review-prompt.md").write_text(prompt, encoding="utf-8")
        pending_file = pending_path(state, tree)
        pending_file.parent.mkdir(parents=True, exist_ok=True)
        pending_file.write_text(json.dumps({
            "tree": tree, "backend": backend,
            "rules": rules_sel,
            "deterministic": det_results,
            "isolation_dir": str(iso),
            "prompt_path": str(reports / "review-prompt.md"),
            "result_path": str(reports / "ai-review.json"),
            "prepared_at": now_iso(),
        }, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "state": "ai-review-required",
            "tree": tree,
            "isolation_dir": str(iso),
            "prompt_path": str(reports / "review-prompt.md"),
            "result_path": str(reports / "ai-review.json"),
            "next": f"code_verify.py static --ai-result \"{reports / 'ai-review.json'}\"",
        }, indent=2))
        return 0
    else:  # claude-code
        rules_sel, rules = load_rules(repo, cfg, args)
        prompt = build_prompt(iso, repo, rules, args.context)
        ai = run_backend_claude(repo, iso, prompt, cfg, reports)
        rec, report = finalize_static(repo, state, tree, cfg, backend,
                                      det_results, ai, rules=rules_sel)

    status = rec["static"]["status"]
    print(f"Static Review: {status}\nReport: {report}")
    if status == "PASS":
        return 0
    return 3 if status == "REVIEW_REQUIRED" else 1


# --------------------------------------------------------------------------
# Stage 2: target
# --------------------------------------------------------------------------

def parse_junit(path: Path):
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    suites = [root] if root.tag == "testsuite" else root.findall(".//testsuite")
    if root.tag == "testsuites" and not suites:
        return None
    agg = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for s in suites:
        for k in agg:
            agg[k] += int(s.get(k, 0) or 0)
    return agg


def cmd_target(args) -> int:
    repo = repo_root_from(Path(args.repo_root))
    state = state_dir(repo)
    cfg = load_config(repo)
    tree = staged_tree(repo)
    target_cfg = cfg.get("target") or {}
    command = target_cfg.get("command") or []

    if args.dry_run:
        rec = load_record(state, tree)
        print(json.dumps({
            "dry_run": True, "tree": tree,
            "static_status": ((rec or {}).get("static") or {}).get("status") if rec else None,
            "target_command": command, "target_id": target_cfg.get("target_id"),
            "kind": target_cfg.get("kind", "unset"),
            "note": "no side effects, no record written",
        }, indent=2))
        return 0

    rec = load_record(state, tree)
    if not rec or not rec.get("static") or rec["static"]["status"] != "PASS":
        print(
            "Target stage requires a static PASS record for the SAME staged "
            f"tree {tree[:12]}...\nRun the static stage first: "
            "code_verify.py static (or /code-verify static).", file=sys.stderr,
        )
        return 2

    if not command:
        raise VerifyError(
            "target validation is not configured (target.command missing in "
            ".code-verify/config.json) — cannot produce any target result"
        )
    kind = target_cfg.get("kind")
    if kind not in ("real", "mock"):
        raise VerifyError("target.kind must be \"real\" or \"mock\" in .code-verify/config.json")

    # Fingerprints are validated BEFORE the target command runs so a missing
    # artifact fails closed without wasting a target cycle (no record).
    art_fps = artifacts_fingerprints(repo, cfg)
    tc_fp = test_config_fingerprint(repo, cfg)
    tg_fp = target_config_fingerprint(target_cfg)

    iso = isolation_dir(repo, tree, state)
    reports = report_dir(state, tree) / "target"
    reports.mkdir(parents=True, exist_ok=True)
    log_path = reports / "target.log"

    env = dict(os.environ, CODE_VERIFY_SNAPSHOT_TREE=tree)
    res = run(command, cwd=iso, timeout=int(target_cfg.get("timeout_sec", 1800)), env=env)
    log_path.write_text(
        f"$ {' '.join(str(c) for c in command)}\ncwd={iso}\n\n{res['output']}",
        encoding="utf-8",
    )

    junit = None
    if target_cfg.get("junit_xml"):
        junit = parse_junit(iso / target_cfg["junit_xml"])

    if res["spawn_error"]:
        status = "INFRA_ERROR"
    elif res["timed_out"]:
        status = "INCONCLUSIVE"
    elif res["exit_code"] != 0:
        status = "FAIL"
    elif junit and (junit["failures"] or junit["errors"]):
        status = "FAIL"
    else:
        status = "PASS"

    release = None
    if target_cfg.get("release_command"):
        release = run(target_cfg["release_command"], cwd=iso,
                      timeout=int(target_cfg.get("release_timeout_sec", 300)), env=env)

    rec["target"] = {
        "status": status,
        "kind": kind,
        "target_id": target_cfg.get("target_id"),
        "artifacts": art_fps,
        "test_suite": command[0] if command else None,
        "test_config_fingerprint": tc_fp,
        "target_config_fingerprint": tg_fp,
        "command": [str(c) for c in command],
        "exit_code": res["exit_code"],
        "timed_out": res["timed_out"],
        "spawn_error": res["spawn_error"],
        "junit": junit,
        "log_dir": str(reports),
        "timestamp": now_iso(),
        "snapshot_tree": tree,
        "release": None if release is None else {
            "exit_code": release["exit_code"], "timed_out": release["timed_out"],
        },
    }
    save_record(state, rec)

    (report_dir(state, tree) / "target.md").write_text("\n".join([
        "# code-verify Target Validation Report", "",
        f"- Snapshot (staged tree): `{tree}`",
        f"- Target: {target_cfg.get('target_id')} (kind: {kind})",
        f"- Artifacts: {rec['target']['artifacts'] or '(none configured)'}",
        f"- Test suite: `{rec['target']['test_suite']}`",
        f"- Status: **{status}**" + (" (timed out)" if res["timed_out"] else ""),
        f"- Exit code: {res['exit_code']}" + (f", spawn error: {res['spawn_error']}" if res["spawn_error"] else ""),
        f"- JUnit: {junit}" if junit else "- JUnit: not configured",
        f"- Logs: `{log_path}`",
        f"- Snapshot tree recorded: `{rec['target']['snapshot_tree']}`",
        "" + (f"- Release command: exit {release['exit_code']}" if release else "- Release command: none"),
    ]) + "\n", encoding="utf-8")

    print(f"Target Validation: {status}\nLogs: {log_path}")
    return 0 if status == "PASS" else 1


# --------------------------------------------------------------------------
# gate / status / hook
# --------------------------------------------------------------------------

def cmd_gate(args) -> int:
    repo = repo_root_from(Path(args.repo_root))
    state = state_dir(repo)
    tree = staged_tree(repo)

    def blocked(reason: str) -> int:
        print(f"Commit Permission: DENIED\nReason: {reason}")
        print("Re-verify: run `code_verify.py static` + `code_verify.py target` "
              "(or /code-verify) with the current staged changes, then commit again.")
        return 1

    try:
        cfg = load_config(repo)
    except VerifyError as exc:
        return blocked(str(exc))
    rec = load_record(state, tree)
    if rec is None:
        return blocked(f"no validation record for staged tree {tree[:12]}...; "
                       "staged content has not been verified")
    static = rec.get("static")
    if not static or static.get("status") != "PASS":
        return blocked(f"static review is {static.get('status') if static else 'missing'}, not PASS")
    target = rec.get("target")
    if not target or target.get("status") != "PASS":
        return blocked("target validation is missing or not PASS")
    if target.get("kind") != "real":
        return blocked("target PASS came from a MOCK run — mock validation "
                       "cannot grant commit permission")
    arts = artifacts_fingerprints(repo, cfg)
    recorded = target.get("artifacts")
    if recorded is not None and [a.get("path") for a in recorded] != [a["path"] for a in arts]:
        return blocked("validated artifacts list changed since target validation")
    recorded_sha = {a.get("path"): a.get("sha256") for a in (recorded or [])}
    for a in arts:
        if a["path"] in recorded_sha and recorded_sha[a["path"]] != a["sha256"]:
            return blocked(f"artifact changed since target validation: {a['path']} "
                           f"({str(recorded_sha[a['path']])[:12]}... -> "
                           f"{a['sha256'][:12]}...)")
    fp = test_config_fingerprint(repo, cfg)
    if target.get("test_config_fingerprint") and fp != target["test_config_fingerprint"]:
        return blocked("test configuration changed since target validation")
    bc_fp = target_config_fingerprint(cfg.get("target") or {})
    if target.get("target_config_fingerprint") and bc_fp != target["target_config_fingerprint"]:
        return blocked("target configuration changed since target validation")
    print(f"Commit Permission: ALLOWED\nSnapshot: {tree}\n"
          f"Static Review: PASS\nTarget Validation: PASS (target {target.get('target_id')})")
    return 0


def cmd_status(args) -> int:
    repo = repo_root_from(Path(args.repo_root))
    state = state_dir(repo)
    tree = staged_tree(repo)
    rec = load_record(state, tree)
    files = changed_files(repo)
    print(f"Repo: {repo}")
    print(f"Base HEAD: {base_head(repo) or '(no commits yet)'}")
    print(f"Staged tree: {tree}")
    for status, paths in files.items():
        for p in paths:
            print(f"  {status} {p}")
    if rec is None:
        print("Validation record: none for this staged tree")
        return 0
    static = rec.get("static")
    target = rec.get("target")
    print(f"Validation record: {record_path(state, tree)}")
    if static:
        print(f"  Static: {static['status']} "
              f"(backend {static['backend']}, {static['timestamp']})")
    else:
        print("  Static: -")
    if target:
        print(f"  Target:  {target['status']} (kind {target['kind']}, "
              f"target {target.get('target_id')}, {target['timestamp']})")
    else:
        print("  Target:  -")
    hp = git(repo, ["config", "core.hooksPath"])
    hooks_path = hp.stdout.decode().strip() if hp.returncode == 0 else ""
    hook_file = repo / ".code-verify" / "hooks" / "pre-commit"
    if hooks_path == ".code-verify/hooks":
        installed = "yes" if hook_file.is_file() else "no (hook file missing)"
    elif hooks_path:
        installed = f"managed by core.hooksPath '{hooks_path}'"
    else:
        installed = "no (core.hooksPath unset)"
    print(f"Hook installed: {installed}")
    return 0


HOOK_SHIM = (
    "#!/bin/sh\n"
    "# code-verify pre-commit gate (installed by `code_verify.py install-hook`).\n"
    "# Only checks the validation record for the current staged tree —\n"
    "# it never runs AI review or target tests inside the hook.\n"
    'state_dir="$(git rev-parse --git-common-dir)/code-verify"\n'
    "PY=python\n"
    "command -v python >/dev/null 2>&1 || PY=python3\n"
    'exec "$PY" "$state_dir/code_verify.py" gate\n'
)


def cmd_install_hook(args) -> int:
    repo = repo_root_from(Path(args.repo_root))
    state = state_dir(repo)
    hooks_rel = ".code-verify/hooks"
    proc = git(repo, ["config", "core.hooksPath"])
    current = proc.stdout.decode().strip() if proc.returncode == 0 else None
    if current and current.strip() != hooks_rel:
        print(
            f"Refusing to overwrite existing hook manager: core.hooksPath "
            f"is already '{current}'. Integrate code-verify into that manager "
            "instead (its pre-commit hook can call: python code_verify.py gate).",
            file=sys.stderr,
        )
        return 2
    hook_path = repo / hooks_rel / "pre-commit"
    refreshing = False
    if hook_path.exists():
        # Byte-identical shim: idempotent refresh (the supported way to
        # update the state copy after a skill update). A foreign hook is
        # never overwritten.
        if hook_path.read_text(encoding="utf-8", errors="replace") != HOOK_SHIM:
            print(
                f"Refusing to overwrite foreign hook: {hook_path} (content "
                "is not the code-verify shim). Integrate code-verify into that "
                "hook instead (call: python code_verify.py gate).",
                file=sys.stderr,
            )
            return 2
        refreshing = True
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text(HOOK_SHIM, encoding="utf-8")
    try:
        hook_path.chmod(0o755)
    except OSError:
        pass
    self_copy = state / "code_verify.py"
    state.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(__file__).resolve(), self_copy)
    if current:
        print(f"core.hooksPath already '{hooks_rel}' (unchanged)")
    else:
        git_out(repo, ["config", "core.hooksPath", hooks_rel])
        print(f"core.hooksPath set to {hooks_rel} (was unset)")
    # Anchor to the repo root: git may answer with a relative git-dir
    # (".git") because it runs with cwd=repo; resolving it against the
    # process cwd would write the exclude into an unrelated location.
    git_dir = Path(git_out(repo, ["rev-parse", "--git-dir"]))
    if not git_dir.is_absolute():
        git_dir = (repo / git_dir).resolve()
    info_exclude = git_dir / "info" / "exclude"
    info_exclude.parent.mkdir(parents=True, exist_ok=True)
    marker = ".code-verify/"
    if info_exclude.is_file():
        content = info_exclude.read_text(encoding="utf-8", errors="replace")
    else:
        content = ""
    if marker not in content.splitlines():
        with open(info_exclude, "a", encoding="utf-8") as f:
            if content and not content.endswith("\n"):
                f.write("\n")
            f.write(f"{marker}\n")
    verb = "refreshed" if refreshing else "installed"
    print(f"Pre-commit hook {verb}: {hook_path}")
    print(f"Hook script copy: {self_copy} (re-run install-hook after skill updates)")
    print(f".code-verify/ ignored via: {info_exclude}")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="code-verify", description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=".", help="target repository")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("snapshot", help="print staged tree snapshot info")

    p_static = sub.add_parser("static", help="Stage 1: static review")
    p_static.add_argument("--backend", choices=AI_BACKENDS, default=None)
    p_static.add_argument("--prepare", action="store_true",
                          help="prepare prompt + pending record and exit "
                               "without any AI call (implied for backend dsh)")
    p_static.add_argument("--ai-result", metavar="FILE",
                          help="dsh backend: finalize from the agent's JSON result file")
    p_static.add_argument("--context", metavar="FILE",
                          help="author intent text injected into the review prompt")
    p_static.add_argument("--rules", metavar="NAME_OR_FILE",
                          help="override review rules (bundled ruleset name or file path)")
    p_static.add_argument("--dry-run", action="store_true")

    p_target = sub.add_parser("target", help="Stage 2: on-target validation")
    p_target.add_argument("--dry-run", action="store_true")

    p_all = sub.add_parser("all", help="static then target (unattended backends only)")
    for flag in ("--backend", "--ai-result", "--context", "--rules", "--dry-run"):
        p_all.add_argument(flag)

    sub.add_parser("gate", help="pre-commit gate: validate record for current staged tree")
    sub.add_parser("status", help="show current snapshot and validation state")
    sub.add_parser("install-hook", help="install the pre-commit gate hook (never overwrites)")

    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            repo = repo_root_from(Path(args.repo_root))
            print(json.dumps({
                "tree": staged_tree(repo),
                "base_head": base_head(repo),
                "files": changed_files(repo),
            }, indent=2))
            return 0
        if args.command == "static":
            return cmd_static(args)
        if args.command == "target":
            return cmd_target(args)
        if args.command == "all":
            cfg = load_config(repo_root_from(Path(args.repo_root)))
            if resolve_backend(cfg, args.backend) == "dsh":
                print(
                    "code-verify ERROR: backend 'dsh' needs the agent in the "
                    "loop; run static --prepare, complete the AI review, "
                    "finalize with --ai-result, then run target.",
                    file=sys.stderr,
                )
                return 2
            rc = cmd_static(args)
            if rc != 0:
                return rc
            return cmd_target(args)
        if args.command == "gate":
            return cmd_gate(args)
        if args.command == "status":
            return cmd_status(args)
        if args.command == "install-hook":
            return cmd_install_hook(args)
    except VerifyError as exc:
        print(f"code-verify ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
