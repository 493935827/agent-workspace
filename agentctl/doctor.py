"""Health checks. Prints PASS / WARN / FAIL. Never prints secret values."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from agentctl import environment as env_mod
from agentctl import gitops, workspace
from agentctl.config import build_effective
from agentctl.links import LinkManager
from agentctl.secrets import check as secrets_check
from agentctl.secrets import env_file_path

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
MIN_PYTHON = (3, 10)


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""


def _tool_version(cmd: str) -> str | None:
    """None = not installed, "" = installed but no version output."""
    if shutil.which(cmd) is None:
        return None
    for args in ([cmd, "--version"], [cmd, "version"]):
        try:
            proc = subprocess.run(
                args, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        out = (proc.stdout or proc.stderr or "").strip()
        if proc.returncode == 0 and out:
            return out.splitlines()[0][:80]
    return ""


def run_checks(root: Path) -> list[Check]:
    checks: list[Check] = []

    def add(name: str, status: str, detail: str = "") -> None:
        checks.append(Check(name, status, detail))

    # workspace structure
    try:
        ver = workspace.read_version(root)
    except workspace.WorkspaceError as e:
        add("workspace", FAIL, str(e))
        return checks
    missing = [d for d in workspace.STRUCTURE_DIRS if not (root / d).is_dir()]
    if missing:
        add("workspace", FAIL, f"missing directories: {', '.join(missing)}")
    else:
        add("workspace", PASS, f"v{ver}, structure complete")

    # environment
    env: str | None = None
    try:
        env, source = env_mod.resolve(root)
        add("environment", PASS, f"{env} (from {source})")
    except env_mod.EnvError as e:
        add("environment", FAIL, str(e))

    cfg = build_effective(root, env)
    enabled = cfg.enabled_skills

    # git
    if not gitops.available():
        add("git", FAIL, "git not found on PATH")
    elif not gitops.is_repo(root):
        add("git", WARN, "not a git repository (run: git init)")
    elif not gitops.has_commits(root):
        add("git", WARN, "repository has no commits yet")
    elif gitops.is_dirty(root):
        lines = gitops.status_lines(root)
        add("git", WARN, f"uncommitted changes ({len(lines)}): {', '.join(lines[:3])}")
    else:
        bits = [gitops.short_commit(root) or "?"]
        if gitops.branch(root):
            bits.append(gitops.branch(root))
        add("git", PASS, " ".join(bits) + " clean")

    # python
    py_ver = sys.version.split()[0]
    if sys.version_info >= MIN_PYTHON:
        add("python", PASS, f"{py_ver} (>= {'.'.join(map(str, MIN_PYTHON))})")
    else:
        add("python", FAIL, f"{py_ver} is older than 3.10")

    # pyyaml (the single runtime dependency)
    try:
        import yaml

        add("pyyaml", PASS, f"yaml {yaml.__version__}")
    except ImportError:
        add("pyyaml", FAIL, "PyYAML missing (online: uv sync; offline: agentctl bootstrap)")

    # tools declared in the profile (git/python always checked above)
    for name in sorted(cfg.tools):
        if name in ("git", "python"):
            continue
        v = _tool_version(name)
        if v is None:
            add(f"tool:{name}", WARN, "not found on PATH")
        elif v == "":
            add(f"tool:{name}", PASS, "present")
        else:
            add(f"tool:{name}", PASS, v)

    # skills
    skills_root = root / "skills"
    missing_skills = [s for s in enabled if not (skills_root / s).is_dir()]
    if not enabled:
        add("skills", WARN, "no skills enabled for this environment")
    elif missing_skills:
        add("skills", FAIL, f"missing skill directories: {', '.join(missing_skills)}")
    else:
        add("skills", PASS, f"{len(enabled)}/{len(enabled)} enabled skills present")

    # links + agent directories
    lm = LinkManager.from_config(root, cfg)
    if not lm.targets:
        add("links", WARN, "no link targets configured (links.targets)")
    else:
        healthy, total, problems = lm.status(enabled)
        if total == 0:
            add("links", WARN, "nothing to link (no enabled skills with sources)")
        elif healthy == total:
            add("links", PASS, f"{healthy}/{total} healthy")
        else:
            add("links", WARN, f"{healthy}/{total} healthy; run: agentctl link")
        for t in lm.targets:
            if not t.parent.is_dir():
                add(f"agent-dir:{t.parent}", WARN,
                    "parent directory missing (agent software installed?)")

    # secrets -- names and SET/MISSING only, never values
    results = secrets_check(root, cfg.required_secrets, cfg.optional_secrets)
    required_set = set(cfg.required_secrets)
    missing_required = [n for n, s in results if not s and n in required_set]
    if not env_file_path(root).is_file() and (cfg.required_secrets or cfg.optional_secrets):
        add("secrets:file", WARN, ".env missing (copy .env.example to .env)")
    if missing_required:
        add("secrets", FAIL, "required: " + ", ".join(f"{n} MISSING" for n in missing_required))
    else:
        optional_set = sum(1 for n, s in results if s and n not in required_set)
        add("secrets", PASS,
            f"required {len(cfg.required_secrets) - len(missing_required)}"
            f"/{len(cfg.required_secrets)} SET, optional {optional_set}"
            f"/{len(cfg.optional_secrets)} SET")

    # optional MCP registry
    mcp = root / "tools" / "mcp-registry.json"
    if mcp.is_file():
        try:
            json.loads(mcp.read_text(encoding="utf-8"))
            add("mcp", PASS, "tools/mcp-registry.json is valid JSON")
        except (json.JSONDecodeError, OSError) as e:
            add("mcp", WARN, f"tools/mcp-registry.json invalid: {e}")
    else:
        add("mcp", PASS, "none configured (see tools/mcp-registry.example.json)")

    return checks


def print_checks(checks: list[Check]) -> int:
    width = max(len(c.name) for c in checks) + 2
    fails = sum(1 for c in checks if c.status == FAIL)
    for c in checks:
        mark = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[c.status]
        print(f"{mark} {c.name.ljust(width)} {c.detail}".rstrip())
    print()
    if fails:
        print(f"{fails} check(s) FAILED")
        return 1
    warns = sum(1 for c in checks if c.status == WARN)
    print("All checks passed" + (f" ({warns} warning(s))" if warns else ""))
    return 0