"""Secret handling. Values are read but NEVER printed or logged."""
from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = ".env"
EXAMPLE_FILE = ".env.example"


def env_file_path(root: Path) -> Path:
    return root / ENV_FILE


def parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def known_secrets(root: Path) -> dict[str, bool]:
    """name -> is_set. Checks .env first, then the process environment."""
    result = {key: bool(value) for key, value in parse_env_file(env_file_path(root)).items()}
    for key in list(result):
        if os.environ.get(key):
            result[key] = True
    return result


def check(root: Path, required: list[str], optional: list[str]) -> list[tuple[str, bool]]:
    """(name, is_set) for required + optional names, in order, deduplicated.

    Only names and booleans leave this module -- never values.
    """
    seen: list[str] = []
    for name in list(required) + list(optional):
        if name not in seen:
            seen.append(name)
    known = known_secrets(root)
    return [(n, bool(known.get(n) or os.environ.get(n))) for n in seen]


def ensure_from_example(root: Path, dry_run: bool = False) -> bool:
    """Create .env from .env.example if missing. Never overwrites."""
    env_p = env_file_path(root)
    if env_p.exists():
        return False
    example = root / EXAMPLE_FILE
    if not example.is_file():
        return False
    if not dry_run:
        env_p.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    return True