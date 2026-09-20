"""agentctl command line interface."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agentctl import __version__
from agentctl import bundle as bundle_mod
from agentctl import config as config_mod
from agentctl import environment as env_mod
from agentctl import gitops, workspace
from agentctl.bootstrap import run_bootstrap
from agentctl.doctor import print_checks, run_checks
from agentctl.links import LinkError, LinkManager
from agentctl.update import run_update
from agentctl.discovery import commands as discovery

ERRORS = (
    workspace.WorkspaceError,
    config_mod.ConfigError,
    env_mod.EnvError,
    gitops.GitError,
    bundle_mod.BundleError,
    LinkError,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agentctl",
        description="Multi-environment Agent workspace manager.",
    )
    p.add_argument("--env", dest="env_global", default=None,
                   help="override environment for this invocation")
    p.add_argument("--root", default=None, help="workspace root (default: auto-detect)")
    p.add_argument("--version", action="version", version=f"agentctl {__version__}")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    sub.add_parser("status", help="show workspace summary")
    sub.add_parser("version", help="show versions")
    sub.add_parser("doctor", help="run health checks (PASS/WARN/FAIL)")

    up = sub.add_parser("update", help="git pull + relink (online environments)")
    up.add_argument("--dry-run", action="store_true")

    bp = sub.add_parser("bootstrap", help="initialize/rebuild this machine's environment")
    bp.add_argument("--env", dest="env", default=None,
                    help="personal | company | intranet (required on first run)")
    bp.add_argument("--dry-run", action="store_true")
    bp.add_argument("--offline", action="store_true",
                    help="force offline dependency install (no network)")

    lp = sub.add_parser("link", help="(re)link enabled skills into agent directories")
    lp.add_argument("--dry-run", action="store_true")
    lp.add_argument("--skill", action="append", help="limit to this skill (repeatable)")

    ulp = sub.add_parser("unlink", help="remove links created by agentctl")
    ulp.add_argument("--skill", action="append", help="limit to this skill (repeatable)")

    ep = sub.add_parser("export", help="build an offline bundle zip")
    ep.add_argument("-o", "--output", default=None, help="output zip path")
    ep.add_argument("--with-wheels", action="store_true",
                    help="pip download python deps into the bundle")
    ep.add_argument("--with-npm", action="store_true",
                    help="npm pack node deps into the bundle")
    ep.add_argument("--dry-run", action="store_true")

    ip = sub.add_parser("import", help="install an offline bundle (intranet path)")
    ip.add_argument("bundle", help="path to agent-workspace-vX.Y.Z-offline.zip")
    ip.add_argument("--env", dest="env", default=None, help="set environment after import")
    ip.add_argument("--dry-run", action="store_true")
    ip.add_argument("--force", action="store_true", help="allow downgrade")

    rp = sub.add_parser("restore", help="restore workspace files from a backup zip")
    rp.add_argument("backup", help="path under backups/ (from a previous import)")

    discovery.add_parsers(sub)
    return p


def _resolve_env(root: Path, args: argparse.Namespace) -> tuple[str, str]:
    override = getattr(args, "env", None) or args.env_global
    return env_mod.resolve(root, override)


# ---------------------------------------------------------------- commands

def cmd_status(root: Path, args: argparse.Namespace) -> int:
    try:
        env, source = _resolve_env(root, args)
    except env_mod.EnvError:
        env, source = None, None
    cfg = config_mod.build_effective(root, env)

    print("Agent Workspace")
    print(f"  Version       {workspace.read_version(root)}")
    if env:
        print(f"  Environment   {env} (from {source})")
    else:
        print("  Environment   (not set - run: agentctl bootstrap --env personal|company|intranet)")

    if gitops.available() and gitops.is_repo(root) and gitops.has_commits(root):
        commit = gitops.short_commit(root) or "-"
        branch = gitops.branch(root) or "-"
        dirty = "dirty" if gitops.is_dirty(root) else "clean"
        ab = gitops.ahead_behind(root)
        if ab is None:
            upd = "no upstream"
        else:
            ahead, behind = ab
            if behind == 0 and ahead == 0:
                upd = "up to date"
            elif behind:
                upd = f"behind {behind}"
            else:
                upd = f"ahead {ahead}"
        print(f"  Commit        {commit} (branch {branch}, {dirty})")
        print(f"  Updates       {upd}")
    else:
        print("  Commit        (no git repository)")

    print(f"  Skills        {len(cfg.enabled_skills)} enabled / "
          f"{workspace.count_dirs(root, 'skills')} available")
    print(f"  Agents        {workspace.count_dirs(root, 'agents')}")

    lm = LinkManager.from_config(root, cfg)
    healthy, total, problems = lm.status(cfg.enabled_skills)
    if total == 0:
        print("  Link Status   no targets or nothing to link")
    elif healthy == total:
        print(f"  Link Status   healthy ({healthy}/{total})")
    else:
        print(f"  Link Status   degraded ({healthy}/{total} healthy)")
        for pr in problems[:5]:
            print(f"                - {pr}")
    return 0


def cmd_version(root: Path, args: argparse.Namespace) -> int:
    print(f"agentctl   {__version__}")
    print(f"workspace  {workspace.read_version(root)}")
    if gitops.available() and gitops.is_repo(root):
        commit = gitops.short_commit(root)
        if commit:
            print(f"commit     {commit}")
    return 0


def cmd_doctor(root: Path, args: argparse.Namespace) -> int:
    return print_checks(run_checks(root))


def cmd_bootstrap(root: Path, args: argparse.Namespace) -> int:
    env = getattr(args, "env", None) or args.env_global
    if not env:
        try:
            env, _ = env_mod.resolve(root)
        except env_mod.EnvError as e:
            print(str(e))
            return 1
    return run_bootstrap(root, env, dry_run=args.dry_run, offline=args.offline)


def cmd_update(root: Path, args: argparse.Namespace) -> int:
    env, _ = _resolve_env(root, args)
    cfg = config_mod.build_effective(root, env)
    return run_update(root, cfg, env, dry_run=args.dry_run)


def cmd_link(root: Path, args: argparse.Namespace) -> int:
    env, _ = _resolve_env(root, args)
    cfg = config_mod.build_effective(root, env)
    skills = cfg.enabled_skills
    if args.skill:
        for s in args.skill:
            if not (root / "skills" / s).is_dir():
                print(f"FAIL unknown skill '{s}'")
                return 1
        skills = list(args.skill)
    lm = LinkManager.from_config(root, cfg)
    actions = lm.plan(skills)
    for line in lm.apply(actions, dry_run=args.dry_run):
        print(line)
    changed = sum(1 for a in actions if a.action not in ("none", "skip"))
    if args.dry_run:
        print(f"[dry-run] {len(actions)} link(s) checked, {changed} change(s) planned")
    else:
        print(f"{len(actions)} link(s) checked, {changed} change(s) applied")
    return 0


def cmd_unlink(root: Path, args: argparse.Namespace) -> int:
    env, _ = _resolve_env(root, args)
    cfg = config_mod.build_effective(root, env)
    skills = list(args.skill) if args.skill else cfg.enabled_skills
    if not skills:
        print("no skills selected; nothing to unlink")
        return 0
    lm = LinkManager.from_config(root, cfg)
    for line in lm.unlink(skills):
        print(line)
    return 0


def cmd_export(root: Path, args: argparse.Namespace) -> int:
    bundle_mod.export_bundle(
        root, output=args.output, with_wheels=args.with_wheels,
        with_npm=args.with_npm, dry_run=args.dry_run,
    )
    return 0


def cmd_import(root: Path, args: argparse.Namespace) -> int:
    return bundle_mod.import_bundle(
        root, args.bundle, environment=getattr(args, "env", None),
        dry_run=args.dry_run, force=args.force,
    )


def cmd_restore(root: Path, args: argparse.Namespace) -> int:
    return bundle_mod.restore_backup(root, args.backup)


HANDLERS = {
    "status": cmd_status,
    "version": cmd_version,
    "doctor": cmd_doctor,
    "update": cmd_update,
    "bootstrap": cmd_bootstrap,
    "link": cmd_link,
    "unlink": cmd_unlink,
    "export": cmd_export,
    "import": cmd_import,
    "restore": cmd_restore,
    **{name: discovery.run for name in discovery.COMMANDS},
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        import yaml  # noqa: F401
    except ImportError:
        print("ERROR: PyYAML is not installed.", file=sys.stderr)
        print("  online : uv sync", file=sys.stderr)
        print("  offline: python -m venv .venv", file=sys.stderr)
        print("           .venv\\Scripts\\pip install --no-index "
              "--find-links packages\\wheels pyyaml", file=sys.stderr)
        return 2

    try:
        start = Path(args.root).expanduser() if args.root else None
        root = workspace.find_root(start)
        return HANDLERS[args.command](root, args)
    except ERRORS as e:
        if args.command in discovery.COMMANDS:
            discovery.emit({"schema_version": 1, "error": "workspace-error"}, args.json)
            return 2
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
