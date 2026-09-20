"""Workspace root discovery, VERSION handling, local directory layout."""
from __future__ import annotations

import os
from pathlib import Path

from agentctl.utils import ensure_dir

try:
    import tomllib
except ImportError:  # Python 3.10
    tomllib = None  # type: ignore[assignment]

VERSION_FILE = "VERSION"

# committed structure
STRUCTURE_DIRS = ("agents", "skills", "configs", "scripts", "tools")
# generated at runtime, gitignored, machine-local
LOCAL_STATE_DIRS = ("packages", "backups", "dist", "manifests")

# keep in sync with pyproject.toml [project].dependencies
FALLBACK_DEPS = ["pyyaml>=6.0", "ruamel.yaml>=0.18,<0.19"]


class WorkspaceError(RuntimeError):
    pass


def _looks_like_workspace(root: Path) -> bool:
    return (root / VERSION_FILE).is_file() and (root / "configs").is_dir()


def find_root(start: Path | None = None) -> Path:
    """Locate the workspace root: AGENT_WORKSPACE_ROOT env var, else walk up."""
    env = os.environ.get("AGENT_WORKSPACE_ROOT")
    if env:
        root = Path(env).expanduser().resolve()
        if not _looks_like_workspace(root):
            raise WorkspaceError(
                f"AGENT_WORKSPACE_ROOT is set to {root}, which is not an agent "
                "workspace (expects a VERSION file and a configs/ directory)."
            )
        return root
    cur = (start or Path.cwd()).resolve()
    if _looks_like_workspace(cur):
        return cur
    for cand in cur.parents:
        if _looks_like_workspace(cand):
            return cand
    raise WorkspaceError(
        "Not inside an agent workspace (no VERSION + configs/ found upwards). "
        "cd into the workspace, or set AGENT_WORKSPACE_ROOT."
    )


def read_version(root: Path) -> str:
    vf = root / VERSION_FILE
    if not vf.is_file():
        raise WorkspaceError(f"VERSION file missing at {vf}")
    text = vf.read_text(encoding="utf-8").strip()
    if not text:
        raise WorkspaceError(f"VERSION file at {vf} is empty")
    return text


def ensure_local_dirs(root: Path) -> list[Path]:
    created = []
    for name in LOCAL_STATE_DIRS:
        p = root / name
        if ensure_dir(p):
            created.append(p)
    return created


def count_dirs(root: Path, subdir: str) -> int:
    base = root / subdir
    if not base.is_dir():
        return 0
    return sum(1 for p in base.iterdir() if p.is_dir() and not p.name.startswith("."))


def python_dependencies(root: Path) -> list[str]:
    """Runtime deps for offline wheels; read from pyproject when possible."""
    if tomllib is not None:
        pyproject = root / "pyproject.toml"
        if pyproject.is_file():
            try:
                data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
                deps = data.get("project", {}).get("dependencies")
                if deps:
                    return [str(d) for d in deps]
            except (tomllib.TOMLDecodeError, OSError):
                pass
    return list(FALLBACK_DEPS)
