"""agentctl update: pull latest from origin (online environments only)."""
from __future__ import annotations

from pathlib import Path

from agentctl import gitops
from agentctl.config import EffectiveConfig
from agentctl.links import LinkManager


def run_update(root: Path, cfg: EffectiveConfig, env: str, dry_run: bool = False) -> int:
    if not cfg.internet:
        print(f"Environment '{env}' is configured offline (network.internet: false).")
        print("Offline machines are updated with a bundle instead:")
        print("  1. on a connected machine: agentctl export --with-wheels")
        print("  2. copy the zip over (USB / allowed channel)")
        print("  3. here: agentctl import agent-workspace-vX.Y.Z-offline.zip")
        return 0

    if not gitops.available():
        print("FAIL git not found on PATH")
        return 1
    if not gitops.is_repo(root):
        print("FAIL not a git repository")
        return 1
    if not gitops.has_commits(root):
        print("FAIL repository has no commits yet")
        return 1

    up = gitops.upstream(root)
    if not up:
        print("FAIL no upstream branch configured.")
        print("Set one with: git push -u origin <branch>")
        return 1

    print("Fetching origin (read-only) ...")
    try:
        gitops.fetch(root)
    except gitops.GitError as e:
        print(f"FAIL {e}")
        return 1

    ab = gitops.ahead_behind(root)
    ahead, behind = ab if ab else (0, 0)
    if behind == 0:
        print(f"Already up to date (ahead {ahead}).")
        return 0

    new_commits = gitops.log_oneline(root, f"HEAD..{up}")
    print(f"{behind} commit(s) incoming:")
    for c in new_commits[:20]:
        print(f"  {c}")
    if len(new_commits) > 20:
        print(f"  ... and {len(new_commits) - 20} more")

    if dry_run:
        print("[dry-run] would run: git pull --ff-only, then re-link skills and check deps")
        return 0

    old = gitops.current_commit(root)
    try:
        gitops.pull_ff_only(root)
    except gitops.GitError as e:
        print(f"FAIL {e}")
        return 1
    new = gitops.current_commit(root)
    print(f"Updated {old[:8] if old else '?'} -> {new[:8] if new else '?'}")

    # dependencies + links
    try:
        import yaml  # noqa: F401

        print("deps: pyyaml importable")
    except ImportError:
        print("WARN pyyaml missing; run: agentctl bootstrap")

    lm = LinkManager.from_config(root, cfg)
    for line in lm.apply(lm.plan(cfg.enabled_skills)):
        print(line)

    print("Done. Run 'agentctl doctor' for a full check.")
    return 0