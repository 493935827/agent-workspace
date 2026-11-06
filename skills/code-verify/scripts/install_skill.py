#!/usr/bin/env python3
"""Install the code-verify skill into an agent runtime's skill directory.

The skill content is identical everywhere; only the install location differs
per agent. Later agents are added to TARGETS — never fork the skill.

Usage:
    python install_skill.py --target dsh            # user level (~/.dsh/skills)
    python install_skill.py --target claude-code    # user level (~/.claude/skills)
    python install_skill.py --target codex          # user level ($CODEX_HOME/skills)
    python install_skill.py --target agents         # user level (~/.agents/skills)
    python install_skill.py --project D:/path/repo [--style dsh|claude-code]
                                                    # project level
    python install_skill.py --target dsh --force    # overwrite an existing copy
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

SKILL_NAME = "code-verify"
HERE = Path(__file__).resolve().parent.parent

TARGETS = {
    "dsh": Path.home() / ".dsh" / "skills",
    "claude-code": Path.home() / ".claude" / "skills",
    "codex": Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "skills",
    "agents": Path.home() / ".agents" / "skills",
}

PROJECT_STYLES = {
    "dsh": ".dsh/skills",
    "claude-code": ".claude/skills",
}


def install(dest_root: Path, force: bool) -> int:
    dest = dest_root / SKILL_NAME
    if dest.exists():
        if not force:
            print(f"already installed: {dest} (use --force to overwrite)")
            return 0
        shutil.rmtree(dest)
    shutil.copytree(HERE, dest, ignore=shutil.ignore_patterns("__pycache__"))
    print(f"installed {SKILL_NAME} -> {dest}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", choices=sorted(TARGETS))
    ap.add_argument("--project", help="install into <project>/.dsh or .claude skills dir")
    ap.add_argument("--style", choices=sorted(PROJECT_STYLES), default="dsh",
                    help="project-level layout style (default: dsh)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if args.project:
        if not (Path(args.project) / ".git").exists():
            print(f"warning: {args.project} is not a git repository root", file=sys.stderr)
        return install(Path(args.project) / PROJECT_STYLES[args.style], args.force)
    if args.target:
        return install(TARGETS[args.target], args.force)
    ap.error("choose --target or --project")


if __name__ == "__main__":
    sys.exit(main())
