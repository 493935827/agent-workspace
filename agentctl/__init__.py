"""agentctl - multi-environment Agent workspace manager.

Lives inside the workspace repository it manages. The workspace VERSION
file (repo root, one level above this package) is the release version.
"""
from __future__ import annotations

import importlib.metadata
from pathlib import Path


def _read_version() -> str:
    version_file = Path(__file__).resolve().parent.parent / "VERSION"
    if version_file.is_file():
        text = version_file.read_text(encoding="utf-8").strip()
        if text:
            return text
    try:
        return importlib.metadata.version("agent-workspace")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0+unknown"


__version__ = _read_version()