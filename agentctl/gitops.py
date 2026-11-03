"""Thin, explicit git wrappers. All output is captured, never streamed."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

# Generous enough for a slow fetch/pull; short enough that a hung git process
# cannot stall the CLI forever.
DEFAULT_TIMEOUT = 120

# scheme://userinfo@ — userinfo (credentials) is masked before it reaches any
# GitError message; scp-like user@host:path is left alone (ambiguous with
# email addresses, and git errors leak credentials via scheme URLs).
_CRED_RE = re.compile(r"([a-zA-Z][a-zA-Z0-9+.\-]*://)([^\s@/]+)@")


def redact(text: str) -> str:
    """Mask userinfo embedded in URLs: https://user:pass@host -> https://***@host."""
    return _CRED_RE.sub(r"\1***@", text)


class GitError(RuntimeError):
    pass


def available() -> bool:
    return shutil.which("git") is not None


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,  # never prompt (credentials, etc.)
            timeout=DEFAULT_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise GitError(f"git {args[0]} timed out after {DEFAULT_TIMEOUT}s") from None
    if check and proc.returncode != 0:
        msg = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
        raise GitError(f"git {args[0]} failed: {redact(msg)}")
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