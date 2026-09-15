"""Idempotent environment bootstrap for a new or existing machine.

Repeated runs must never damage the environment: every step either
verifies, creates-if-missing, or refreshes links.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from agentctl import environment as env_mod
from agentctl import gitops, workspace
from agentctl.config import build_effective
from agentctl.doctor import print_checks, run_checks
from agentctl.links import LinkManager
from agentctl.secrets import ensure_from_example


def venv_python(root: Path) -> Path:
    rel = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    return root / ".venv" / rel


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def install_deps(root: Path, offline: bool, dry_run: bool) -> list[str]:
    """Ensure a .venv with the runtime deps. Returns log lines."""
    log: list[str] = []
    deps = workspace.python_dependencies(root)
    vpy = venv_python(root)

    if shutil.which("uv") and not offline:
        if dry_run:
            log.append("[dry-run] uv sync")
            return log
        proc = _run(["uv", "sync"], cwd=root)
        if proc.returncode == 0:
            log.append(f"uv sync ok (deps: {', '.join(deps)})")
            return log
        log.append(f"WARN uv sync failed, falling back to venv+pip: "
                   f"{(proc.stderr or proc.stdout).strip()[:200]}")

    if not vpy.is_file():
        if dry_run:
            log.append("[dry-run] python -m venv .venv")
            log.append(f"[dry-run] pip install {'--no-index (offline)' if offline else ''} "
                       f"{', '.join(deps)}")
            return log
        proc = _run([sys.executable, "-m", "venv", str(root / ".venv")], cwd=root)
        if proc.returncode != 0:
            log.append(f"FAIL creating venv: {(proc.stderr or proc.stdout).strip()[:200]}")
            return log
        log.append("created .venv")

    pip_args = [str(vpy), "-m", "pip", "install", "--quiet"]
    if offline:
        pip_args += ["--no-index", "--find-links", str(root / "packages" / "wheels")]
    pip_args += deps
    if dry_run:
        log.append("[dry-run] " + " ".join(pip_args))
        return log
    proc = _run(pip_args, cwd=root)
    if proc.returncode != 0:
        log.append(f"FAIL pip install: {(proc.stderr or proc.stdout).strip()[:300]}")
        if offline:
            log.append("hint: import an offline bundle built with --with-wheels first")
        return log
    log.append(f"{'offline ' if offline else ''}pip install ok ({', '.join(deps)})")
    return log


def run_bootstrap(root: Path, environment: str, dry_run: bool = False,
                  offline: bool = False) -> int:
    print(f"Bootstrapping workspace at {root}")
    print(f"Environment: {environment}{' (dry-run)' if dry_run else ''}")
    print()

    # 1. git repository
    if gitops.available():
        if not gitops.is_repo(root):
            if dry_run:
                print("[dry-run] git init")
            else:
                gitops.init(root)
                print("git repository initialized")
    else:
        print("WARN git not found; skipping repository init")

    # 2. environment marker (local.yaml, gitignored)
    changed = env_mod.set_environment(root, environment, dry_run=dry_run)
    print(f"environment {'set to' if changed else 'already set to'} {environment} (local.yaml)")

    # 3. local state directories
    if dry_run:
        print(f"[dry-run] ensure dirs: {', '.join(workspace.LOCAL_STATE_DIRS)}")
    else:
        created = workspace.ensure_local_dirs(root)
        if created:
            print(f"created dirs: {', '.join(p.name for p in created)}")

    # 4. .env skeleton
    if ensure_from_example(root, dry_run=dry_run):
        print("created .env from .env.example (fill in your secrets)")
    else:
        print(".env already present or no example")

    # 5. python dependencies
    cfg = build_effective(root, environment)
    if not offline:
        offline = not cfg.internet
    for line in install_deps(root, offline=offline, dry_run=dry_run):
        print(line)

    # 6. skill links
    lm = LinkManager.from_config(root, cfg)
    for line in lm.apply(lm.plan(cfg.enabled_skills), dry_run=dry_run):
        print(line)

    # 7. doctor
    print()
    if dry_run:
        print("[dry-run] doctor skipped")
        return 0
    print("Running doctor ...")
    return print_checks(run_checks(root))