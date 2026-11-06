#!/usr/bin/env python3
"""code-verify offline self-test.

Runs the deterministic core (code_verify.py) against throwaway temp git
repositories with stub deterministic/AI/target commands. Never touches real
hardware, never spawns the claude CLI, never produces a record outside the
temp repos. Cover: two-stage PASS allow, static FAIL, blocker finding,
REVIEW_REQUIRED, target FAIL, target INFRA_ERROR, snapshot invalidation,
unstaged isolation, AI failure fail-closed, mock rejection, hook block/allow,
timeout cleanup, install-hook refresh + foreign-hook refusal, install-hook
from a non-repo cwd, BOM config, target-config invalidation, rules selection,
missing rules fail-closed, old-schema record rejection, artifact
invalidation, SKILL.md frontmatter catalog safety.

Usage: python selftest.py [--keep]
Exit 0 when every case passes.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FW = Path(__file__).resolve().parent / "code_verify.py"
PY = sys.executable
RESULTS: list[tuple[str, bool, str]] = []


def sh(cmd, cwd, check=True, env_extra=None):
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                          env={**os.environ, **(env_extra or {})})
    if check and proc.returncode != 0:
        raise AssertionError(f"cmd failed {cmd}: {proc.stdout}\n{proc.stderr}")
    return proc


def fw(repo, *args, check=True):
    return sh([PY, str(FW), "--repo-root", str(repo), *args], cwd=repo, check=check)


def git(repo, *args, check=True):
    return sh(["git", *args], cwd=repo, check=check)


def make_repo(tmp: Path, name: str) -> Path:
    repo = tmp / name
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    (repo / "app.py").write_text("print('v1')\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    return repo


def write_config(repo: Path, **overrides):
    cfg = {
        "ai_backend": "dsh",
        "static_commands": [[PY, "-c", "print('det ok')"]],
        "static_timeout_sec": 60,
        "target": {
            "kind": "real",
            "target_id": "SELFTEST-BAY",
            "command": [PY, "-c", "print('target ok')"],
            "timeout_sec": 30,
            "release_command": [],
            "junit_xml": None,
        },
        "artifacts": [],
        "test_config_files": [],
    }
    for key, value in overrides.items():
        if key == "target":
            cfg["target"].update(value)
        else:
            cfg[key] = value
    d = repo / ".code-verify"
    d.mkdir(exist_ok=True)
    (d / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def stage_new_version(repo: Path, text: str):
    (repo / "app.py").write_text(text, encoding="utf-8")
    git(repo, "add", "app.py")


def ai_result(path: Path, verdict="PASS", findings=None, risks=None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "verdict": verdict, "summary": "stub",
        "findings": findings or [], "risks": risks or [],
        "claude_md_files": [], "notes": "selftest stub",
    }, indent=2), encoding="utf-8")
    return path


def run_static_dsh_pass(repo: Path, tmp: Path) -> str:
    out = fw(repo, "static", "--prepare", "--backend", "dsh")
    info = json.loads(out.stdout)
    fw(repo, "static", "--ai-result", str(ai_result(tmp / f"{repo.name}-ai.json")))
    return info["tree"]


def case(name):
    def deco(fn):
        def wrapper(tmp: Path):
            try:
                fn(tmp)
                RESULTS.append((name, True, ""))
            except Exception as exc:  # noqa: BLE001 — test harness
                RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))
        return wrapper
    return deco


@case("1 two-stage PASS -> commit allowed")
def c1(tmp):
    repo = make_repo(tmp, "t1")
    stage_new_version(repo, "print('v2')\n")
    write_config(repo)
    run_static_dsh_pass(repo, tmp)
    fw(repo, "target")
    gate = fw(repo, "gate")
    assert "ALLOWED" in gate.stdout, gate.stdout


@case("2 static FAIL blocks target stage")
def c2(tmp):
    repo = make_repo(tmp, "t2")
    stage_new_version(repo, "print('v2')\n")
    write_config(repo, static_commands=[[PY, "-c", "import sys; sys.exit(3)"]])
    r = fw(repo, "static", "--backend", "dsh", check=False)
    assert r.returncode == 1 and "FAIL" in r.stdout, (r.returncode, r.stdout)
    b = fw(repo, "target", check=False)
    assert b.returncode == 2 and "static PASS" in b.stderr, (b.returncode, b.stderr)


@case("3 verified blocker finding -> gate denied")
def c3(tmp):
    repo = make_repo(tmp, "t3")
    stage_new_version(repo, "print('v2')\n")
    write_config(repo)
    fw(repo, "static", "--prepare", "--backend", "dsh")
    result = ai_result(tmp / "t3-ai.json", verdict="FAIL", findings=[{
        "id": "F1", "file": "app.py", "line": 1, "severity": "blocker",
        "category": "bug", "description": "stub blocker", "trigger_condition": "always",
        "evidence": "print", "suggested_fix": "fix", "verified": True,
    }])
    r = fw(repo, "static", "--ai-result", str(result), check=False)
    assert r.returncode == 1 and "FAIL" in r.stdout, (r.returncode, r.stdout)
    gate = fw(repo, "gate", check=False)
    assert gate.returncode == 1 and "not PASS" in gate.stdout, gate.stdout


@case("4 REVIEW_REQUIRED blocks auto target")
def c4(tmp):
    repo = make_repo(tmp, "t4")
    stage_new_version(repo, "print('v2')\n")
    write_config(repo)
    fw(repo, "static", "--prepare", "--backend", "dsh")
    result = ai_result(tmp / "t4-ai.json", verdict="PASS", risks=[{
        "id": "R1", "file": "app.py", "line": 1, "reason": "timing",
        "description": "cannot prove statically",
        "what_to_check_on_target": "scope",
    }])
    r = fw(repo, "static", "--ai-result", str(result), check=False)
    assert r.returncode == 3 and "REVIEW_REQUIRED" in r.stdout, (r.returncode, r.stdout)
    b = fw(repo, "target", check=False)
    assert b.returncode == 2, (b.returncode, b.stderr)


@case("5 target FAIL -> gate denied")
def c5(tmp):
    repo = make_repo(tmp, "t5")
    stage_new_version(repo, "print('v2')\n")
    write_config(repo, target={"command": [PY, "-c", "import sys; sys.exit(1)"]})
    run_static_dsh_pass(repo, tmp)
    b = fw(repo, "target", check=False)
    assert b.returncode == 1 and "FAIL" in b.stdout, (b.returncode, b.stdout)
    gate = fw(repo, "gate", check=False)
    assert gate.returncode == 1 and "not PASS" in gate.stdout, gate.stdout


@case("6 target unavailable -> INFRA_ERROR, no success record")
def c6(tmp):
    repo = make_repo(tmp, "t6")
    stage_new_version(repo, "print('v2')\n")
    write_config(repo, target={"command": ["definitely-missing-target-binary-xyz"]})
    run_static_dsh_pass(repo, tmp)
    b = fw(repo, "target", check=False)
    assert b.returncode == 1 and "INFRA_ERROR" in b.stdout, (b.returncode, b.stdout)
    gate = fw(repo, "gate", check=False)
    assert gate.returncode == 1, gate.stdout


@case("7 re-staging invalidates the verified record")
def c7(tmp):
    repo = make_repo(tmp, "t7")
    stage_new_version(repo, "print('v2')\n")
    write_config(repo)
    run_static_dsh_pass(repo, tmp)
    fw(repo, "target")
    stage_new_version(repo, "print('v3 changed')\n")
    gate = fw(repo, "gate", check=False)
    assert gate.returncode == 1 and "no validation record" in gate.stdout, gate.stdout


@case("8 unstaged changes stay out of the verified snapshot")
def c8(tmp):
    repo = make_repo(tmp, "t8")
    stage_new_version(repo, "print('v2 staged')\n")
    write_config(repo)
    (repo / "app.py").write_text("print('v2 UNSTAGED DIRTY')\n", encoding="utf-8")
    out = fw(repo, "static", "--prepare", "--backend", "dsh")
    info = json.loads(out.stdout)
    iso_file = Path(info["isolation_dir"]) / "app.py"
    assert iso_file.read_text(encoding="utf-8") == "print('v2 staged')\n"
    assert "UNSTAGED" not in Path(info["prompt_path"]).read_text(encoding="utf-8")


@case("9 AI failure never yields PASS")
def c9(tmp):
    repo = make_repo(tmp, "t9a")
    stage_new_version(repo, "print('v2')\n")
    write_config(repo)
    fw(repo, "static", "--prepare", "--backend", "dsh")
    bad = tmp / "t9-garbage.json"
    bad.write_text("this is not json at all", encoding="utf-8")
    r = fw(repo, "static", "--ai-result", str(bad), check=False)
    assert r.returncode == 2 and "ERROR" in r.stderr, (r.returncode, r.stderr)
    gate = fw(repo, "gate", check=False)
    assert gate.returncode == 1, "garbage AI result must not unlock the gate"
    # claude backend with missing binary fails closed
    repo2 = make_repo(tmp, "t9b")
    stage_new_version(repo2, "print('v2')\n")
    write_config(repo2, ai_backend="claude-code", claude_bin="definitely-missing-claude-xyz")
    r2 = fw(repo2, "static", "--backend", "claude-code", check=False)
    assert r2.returncode == 2 and "claude CLI not found" in r2.stderr, (r2.returncode, r2.stderr)


@case("10 mock target PASS is rejected by the gate")
def c10(tmp):
    repo = make_repo(tmp, "t10")
    stage_new_version(repo, "print('v2')\n")
    write_config(repo, target={"kind": "mock"})
    run_static_dsh_pass(repo, tmp)
    fw(repo, "target")
    gate = fw(repo, "gate", check=False)
    assert gate.returncode == 1 and "MOCK" in gate.stdout, gate.stdout


@case("11 pre-commit hook blocks unverified commit, allows verified")
def c11(tmp):
    repo = make_repo(tmp, "t11")
    stage_new_version(repo, "print('v2')\n")
    write_config(repo)
    fw(repo, "install-hook")
    blocked = git(repo, "commit", "-m", "should fail", check=False)
    assert blocked.returncode != 0 and "DENIED" in blocked.stderr + blocked.stdout, (
        blocked.returncode, blocked.stdout, blocked.stderr)
    run_static_dsh_pass(repo, tmp)
    fw(repo, "target")
    ok = git(repo, "commit", "-m", "verified", check=False)
    assert ok.returncode == 0, (ok.returncode, ok.stdout, ok.stderr)


@case("12 target timeout -> INCONCLUSIVE + release runs")
def c12(tmp):
    repo = make_repo(tmp, "t12")
    stage_new_version(repo, "print('v2')\n")
    write_config(repo, target={
        "command": [PY, "-c", "import time; time.sleep(30)"],
        "timeout_sec": 2, "release_command": [PY, "-c", "print('released')"],
    })
    run_static_dsh_pass(repo, tmp)
    b = fw(repo, "target", check=False)
    assert b.returncode == 1 and "INCONCLUSIVE" in b.stdout, (b.returncode, b.stdout)
    rec_path = repo / ".git" / "code-verify" / "records"
    recs = [p for p in rec_path.glob("*.json") if not p.name.endswith(".pending.json")]
    assert recs, "timeout must still produce a record"
    rec = json.loads(recs[0].read_text(encoding="utf-8"))
    assert rec["target"]["timed_out"] is True and rec["target"]["release"]["exit_code"] == 0


@case("13 install-hook refreshes its own shim, refuses foreign hooks")
def c13(tmp):
    repo = make_repo(tmp, "t13")
    stage_new_version(repo, "print('v2')\n")
    write_config(repo)
    fw(repo, "install-hook")
    # simulate a skill update after the first install: the state copy is stale
    state_copy = repo / ".git" / "code-verify" / "code_verify.py"
    state_copy.write_text("# stale copy\n", encoding="utf-8")
    r = fw(repo, "install-hook", check=False)
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert state_copy.read_text(encoding="utf-8") == FW.read_text(encoding="utf-8"), (
        "re-running install-hook must refresh the core-script copy")
    # a foreign pre-commit hook is still refused (and nothing is installed)
    repo2 = make_repo(tmp, "t13b")
    stage_new_version(repo2, "print('v2')\n")
    write_config(repo2)
    hook = repo2 / ".code-verify" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\necho custom manager\n", encoding="utf-8")
    r2 = fw(repo2, "install-hook", check=False)
    assert r2.returncode == 2 and "Refusing" in r2.stderr, (r2.returncode, r2.stderr)
    assert not (repo2 / ".git" / "code-verify" / "code_verify.py").exists(), (
        "a refused install must not copy the core script")
    exclude = repo2 / ".git" / "info" / "exclude"
    assert not (exclude.is_file() and ".code-verify/" in exclude.read_text(encoding="utf-8")), (
        "a refused install must not touch .git/info/exclude")


@case("14 install-hook anchors .git paths to the repo, not the process cwd")
def c14(tmp):
    repo = make_repo(tmp, "t14")
    stage_new_version(repo, "print('v2')\n")
    write_config(repo)
    away = tmp / "away-cwd"
    away.mkdir(exist_ok=True)
    proc = sh([PY, str(FW), "--repo-root", str(repo), "install-hook"],
              cwd=away, check=False)
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    exclude = repo / ".git" / "info" / "exclude"
    assert ".code-verify/" in exclude.read_text(encoding="utf-8"), (
        "exclude marker must land in the TARGET repo, not the process cwd")
    assert not (away / ".git").exists(), (
        "running from a foreign cwd must not create stray .git paths there")


@case("15 config.json with a UTF-8 BOM loads")
def c15(tmp):
    repo = make_repo(tmp, "t15")
    stage_new_version(repo, "print('v2')\n")
    write_config(repo)
    cfg_path = repo / ".code-verify" / "config.json"
    cfg_path.write_bytes(b"\xef\xbb\xbf" + cfg_path.read_bytes())
    out = fw(repo, "static", "--prepare", "--backend", "dsh")
    info = json.loads(out.stdout)
    assert info["state"] == "ai-review-required" and info["tree"], out.stdout


@case("16 target config change invalidates the target PASS record")
def c16(tmp):
    repo = make_repo(tmp, "t16")
    stage_new_version(repo, "print('v2')\n")
    write_config(repo)
    run_static_dsh_pass(repo, tmp)
    fw(repo, "target")
    gate = fw(repo, "gate")
    assert "ALLOWED" in gate.stdout, gate.stdout
    # a different target config (here: another target_id) must not inherit the
    # old PASS — the gate fingerprints the whole target block
    write_config(repo, target={"target_id": "CHANGED-BAY"})
    gate2 = fw(repo, "gate", check=False)
    assert gate2.returncode == 1 and "target configuration changed" in gate2.stdout, (
        gate2.returncode, gate2.stdout)


@case("17 review_rules selects a repo-relative rules file")
def c17(tmp):
    repo = make_repo(tmp, "t17")
    stage_new_version(repo, "print('v2')\n")
    (repo / "my-rules.md").write_text(
        "RULES-MARKER-C17: only flag issues citing this marker\n", encoding="utf-8")
    write_config(repo, review_rules="my-rules.md")
    out = fw(repo, "static", "--prepare", "--backend", "dsh")
    info = json.loads(out.stdout)
    prompt = Path(info["prompt_path"]).read_text(encoding="utf-8")
    assert "RULES-MARKER-C17" in prompt, "custom rules must be injected into the prompt"
    assert "{{PROJECT_RULES}}" not in prompt, "placeholder must be fully replaced"


@case("18 missing rules file fails closed")
def c18(tmp):
    repo = make_repo(tmp, "t18")
    stage_new_version(repo, "print('v2')\n")
    write_config(repo, review_rules="missing-rules.md")
    r = fw(repo, "static", "--prepare", "--backend", "dsh", check=False)
    assert r.returncode == 2 and "review rules file not found" in r.stderr, (
        r.returncode, r.stderr)


@case("19 old-schema (v1) records are ignored, gate stays closed")
def c19(tmp):
    repo = make_repo(tmp, "t19")
    stage_new_version(repo, "print('v2')\n")
    write_config(repo)
    run_static_dsh_pass(repo, tmp)
    fw(repo, "target")
    gate = fw(repo, "gate")
    assert "ALLOWED" in gate.stdout, gate.stdout
    rec_path = repo / ".git" / "code-verify" / "records"
    recs = [p for p in rec_path.glob("*.json") if not p.name.endswith(".pending.json")]
    assert recs, "expected a validation record"
    rec = json.loads(recs[0].read_text(encoding="utf-8"))
    rec["schema"] = 1  # simulate a legacy fw-verify v1 record
    recs[0].write_text(json.dumps(rec, indent=2), encoding="utf-8")
    gate2 = fw(repo, "gate", check=False)
    assert gate2.returncode == 1 and "no validation record" in gate2.stdout, gate2.stdout


@case("20 artifact change invalidates the target PASS record")
def c20(tmp):
    repo = make_repo(tmp, "t20")
    stage_new_version(repo, "print('v2')\n")
    (repo / "fw.bin").write_bytes(b"\x01\x02\x03")
    write_config(repo, artifacts=["fw.bin"])
    run_static_dsh_pass(repo, tmp)
    fw(repo, "target")
    gate = fw(repo, "gate")
    assert "ALLOWED" in gate.stdout, gate.stdout
    (repo / "fw.bin").write_bytes(b"\x01\x02\x04")
    gate2 = fw(repo, "gate", check=False)
    assert gate2.returncode == 1 and "artifact changed" in gate2.stdout, gate2.stdout


@case("21 SKILL.md frontmatter is valid catalog YAML")
def c21(tmp):
    # Regression guard: an unquoted ': ' inside a frontmatter scalar makes the
    # YAML parser reject the whole file, and the DSH skill registry silently
    # drops the skill from the session catalog (observed 2026-11-03 when the
    # description contained "(review_rules: firmware-board)"). Offline check
    # without PyYAML: line-level invariants that mirror the parser rule.
    skill_md = FW.parent.parent / "SKILL.md"
    raw = skill_md.read_text(encoding="utf-8-sig")
    lines = raw.splitlines()
    assert lines and lines[0].strip() == "---", "SKILL.md must open with '---'"
    closers = [i for i in range(1, len(lines)) if lines[i].strip() == "---"]
    assert closers, "frontmatter is never closed with '---'"
    meta = lines[1:closers[0]]
    fields = {}
    for line in meta:
        assert ":" in line, f"frontmatter line lacks 'key: value': {line!r}"
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value[:1] not in {'"', "'"}:
            # Unquoted scalars must not contain ': ' (nested compact mapping)
            # nor end with ':' — both make DSH's YAML parser reject the file.
            assert ": " not in value and not value.endswith(":"), (
                f"unquoted frontmatter value for {key!r} contains ': ' — "
                f"quote it or reword: {value!r}")
        fields[key] = value
    assert fields.get("name") == "code-verify", fields.get("name")
    assert len(fields.get("description", "")) > 20, "description must be present"


def main() -> int:
    keep = "--keep" in sys.argv
    tmp = Path(tempfile.mkdtemp(prefix="code-verify-selftest-"))
    print(f"selftest workspace: {tmp}")
    try:
        import py_compile
        py_compile.compile(str(FW), doraise=True)
        for fn in (c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12,
                   c13, c14, c15, c16, c17, c18, c19, c20, c21):
            fn(tmp)
    finally:
        passed = [n for n, ok, _ in RESULTS if ok]
        failed = [(n, err) for n, ok, err in RESULTS if not ok]
        print(f"\n===== {len(passed)} passed, {len(failed)} failed =====")
        for name, err in failed:
            print(f"FAIL {name}\n      {err}")
        for name in passed:
            print(f"ok   {name}")
        if not keep and not failed:
            shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    main()
