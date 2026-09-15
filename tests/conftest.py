"""Shared fixtures. Tests build throwaway workspaces under pytest tmp_path;
the real user agent directories are never touched."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def make_workspace(tmp: Path, version: str = "0.1.0") -> Path:
    """Minimal but complete workspace pointing link targets at a sandbox."""
    root = tmp / "ws"
    for d in ("configs", "tools", "scripts"):
        (root / d).mkdir(parents=True)
    for skill in ("alpha", "beta", "gamma"):
        (root / "skills" / skill).mkdir(parents=True)
        (root / "skills" / skill / "SKILL.md").write_text(
            f"---\nname: {skill}\n---\n# {skill}\n", encoding="utf-8")
    (root / "agents" / "example").mkdir(parents=True)
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")

    sandbox = (tmp / "agent-skills").as_posix()
    (root / "configs" / "common.yaml").write_text(
        "skills:\n"
        "  - alpha\n"
        "  - beta\n"
        "links:\n"
        "  strategy: copy\n"
        "  targets:\n"
        f"    - {sandbox}\n"
        "secrets:\n"
        "  required: [TOKEN_A]\n"
        "  optional: [TOKEN_B]\n",
        encoding="utf-8",
    )
    (root / "configs" / "personal.yaml").write_text("skills:\n  - gamma\n", encoding="utf-8")
    (root / "configs" / "company.yaml").write_text(
        "skills: []\nexclude_skills:\n  - beta\n", encoding="utf-8")
    return root


@pytest.fixture
def ws(tmp_path):
    return make_workspace(tmp_path)