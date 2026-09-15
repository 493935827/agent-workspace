"""Thin, explicit git wrappers. All output is captured, never streamed."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def available() -> bool:
    return shutil.which("git") is not None


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        msg = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
        raise GitError(f"git {args[0]} failed: {msg}")
    return proc


def is_repo(root: Path) -> bool:
    if not available():
        return False
    return _git(root, "rev-parse", "--is-inside-work-tree", check=False).returncode == 0


def has_commits(root: Path) -> bool:
    return _git(root, "rev-parse", "--verify", "HEAD", check=False).returncode == 0


def current_commit(root: Path) -> str | None:
    proc = _git(root, "rev-parse", "HEAD", check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def short_commit(root: Path) -> str | None:
    proc = _git(root, "rev-parse", "--short", "HEAD", check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def branch(root: Path) -> str | None:
    proc = _git(root, "rev-parse", "--abbrev-ref", "HEAD", check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def is_dirty(root: Path) -> bool:
    return bool(_git(root, "status", "--porcelain", check=False).stdout.strip())


def status_lines(root: Path) -> list[str]:
    proc = _git(root, "status", "--porcelain", check=False)
    return [l.strip() for l in proc.stdout.splitlines() if l.strip()]


def upstream(root: Path) -> str | None:
    proc = _git(
        root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def ahead_behind(root: Path) -> tuple[int, int] | None:
    up = upstream(root)
    if not up:
        return None
    proc = _git(root, "rev-list", "--left-right", "--count", f"HEAD...{up}", check=False)
    if proc.returncode != 0:
        return None
    try:
        ahead_s, behind_s = proc.stdout.split()
        return int(ahead_s), int(behind_s)
    except ValueError:
        return None


def tracked_files(root: Path) -> list[str]:
    proc = _git(root, "ls-files", "-z", check=False)
    if proc.returncode != 0:
        return []
    return [p for p in proc.stdout.split("\0") if p]


def fetch(root: Path) -> subprocess.CompletedProcess:
    return _git(root, "fetch", "--quiet")


def pull_ff_only(root: Path) -> subprocess.CompletedProcess:
    return _git(root, "pull", "--ff-only", "--quiet")


def log_oneline(root: Path, rev_range: str) -> list[str]:
    proc = _git(root, "log", "--oneline", rev_range, check=False)
    if proc.returncode != 0:
        return []
    return [l for l in proc.stdout.splitlines() if l.strip()]


def init(root: Path) -> None:
    if not is_repo(root):
        _git(root, "init")