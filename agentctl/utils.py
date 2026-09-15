"""Small shared helpers: hashing, timestamps, backups, zip safety."""
from __future__ import annotations

import hashlib
import os
import shutil
import time
from pathlib import Path

TS_FMT = "%Y%m%d-%H%M%S"


def now_ts() -> str:
    return time.strftime(TS_FMT)


def shasum(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_dir(path: Path) -> bool:
    """Create a directory (with parents) if missing. True if created now."""
    if path.is_dir():
        return False
    path.mkdir(parents=True, exist_ok=True)
    return True


def backup_path(src: Path, backup_root: Path) -> Path | None:
    """Move an existing path into backup_root with a timestamp suffix.

    Never deletes anything; used before replacing foreign directories.
    """
    if not src.exists() and not src.is_symlink():
        return None
    ensure_dir(backup_root)
    dst = backup_root / f"{src.name}.{now_ts()}"
    if dst.exists():
        dst = backup_root / f"{src.name}.{now_ts()}.{os.getpid()}"
    shutil.move(str(src), str(dst))
    return dst


def safe_zip_parts(member: str) -> list[str] | None:
    """Validate a zip entry name; return its parts, or None if unsafe.

    Rejects absolute paths, drive letters, '..' and empty segments.
    """
    name = member.replace("\\", "/")
    if name.startswith("/"):
        return None
    parts = name.split("/")
    if not parts or parts[0] == "":
        return None
    if ":" in parts[0]:  # windows drive letter / absolute
        return None
    for p in parts:
        if p in ("", ".", ".."):
            return None
    if any(ord(c) < 32 for c in name):
        return None
    return parts