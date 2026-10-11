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
        description="管理多环境 Agent 工作区：初始化、Skill 链接、在线更新、离线迁移与本机资源盘点。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "使用示例:\n"
            "  agentctl bootstrap --env personal --dry-run  预览个人环境初始化\n"
            "  agentctl status                            查看工作区及链接状态\n"
            "  agentctl doctor                            检查工作区（doctor 是子命令）\n"
            "  agentctl --env company diff --full --check 检查公司环境的资源差异\n"
            "  agentctl export --with-wheels              制作含 Python 依赖的离线包\n"
            "\n"
            "运行 agentctl COMMAND --help 查看子命令的参数、示例和注意事项。\n"
            "全局 --env、--root 放在 COMMAND 前；子命令自己的参数放在 COMMAND 后。"
        ),
    )
    p.add_argument("--env", dest="env_global", default=None,
                   metavar="ENV", help="读取有效配置时指定环境；优先于 AGENTCTL_ENV 和 local.yaml")
    p.add_argument("--root", default=None, metavar="PATH",
                   help="工作区查找起点；AGENT_WORKSPACE_ROOT 已设置时优先使用该变量，否则从此路径或当前目录向上查找")
    p.add_argument("--version", action="version", version=f"agentctl {__version__}",
                   help="显示 agentctl 版本并退出")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    sub.add_parser("status", help="显示版本、环境、Git、Skill 与链接概况",
                   description="显示工作区版本、环境来源、Git 状态、Skill 数量和链接健康度。",
                   epilog="示例: agentctl status")
    sub.add_parser("version", help="显示 CLI、工作区和 Git 版本",
                   description="显示 agentctl 版本、工作区 VERSION，以及可用时的 Git 提交。",
                   epilog="示例: agentctl version\n仅查看 CLI 版本也可用 agentctl --version。",
                   formatter_class=argparse.RawDescriptionHelpFormatter)
    sub.add_parser("doctor", help="检查工作区健康状况",
                   description="执行工作区检查，并按 PASS/WARN/FAIL 输出结果。",
                   epilog="示例: agentctl doctor")

    up = sub.add_parser("update", help="从 Git 更新并刷新 Skill 链接",
                        description="联网环境先 fetch，再以 --ff-only 拉取上游提交，并刷新 Skill 链接。",
                        epilog="示例: agentctl update --dry-run\n离线环境会提示使用 export/import，不执行网络更新。",
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    up.add_argument("--dry-run", action="store_true",
                    help="仍执行只读 fetch 并列出待拉取提交；不 pull 或刷新链接")

    bp = sub.add_parser("bootstrap", help="初始化或重建本机工作环境",
                        description="设置环境标记，准备本地目录、.env 模板和 Python 依赖，刷新 Skill 链接并运行 doctor。",
                        epilog="示例: agentctl bootstrap --env personal --dry-run\n首次使用须指定 --env；已有环境可从 AGENTCTL_ENV 或 local.yaml 读取。",
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    bp.add_argument("--env", dest="env", default=None,
                    metavar="ENV", help="要写入 local.yaml 的环境，如 personal、company、intranet")
    bp.add_argument("--dry-run", action="store_true", help="预览操作，不写入本地文件或安装依赖")
    bp.add_argument("--offline", action="store_true",
                    help="强制从 packages/wheels 离线安装 Python 依赖")

    lp = sub.add_parser("link", help="建立或刷新启用的 Skill 链接",
                        description="按当前环境配置，将 skills/ 中的 Skill 链接到 Agent 工具目录。",
                        epilog="示例: agentctl link --skill python-helper --dry-run\n不指定 --skill 时处理当前环境启用的全部 Skill。",
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    lp.add_argument("--dry-run", action="store_true", help="只显示计划的链接变更")
    lp.add_argument("--skill", action="append", metavar="NAME",
                    help="只处理指定 Skill；可重复传入，须为 skills/ 下现有目录")

    ulp = sub.add_parser("unlink", help="移除 agentctl 管理的 Skill 链接",
                         description="移除当前环境中由 agentctl 管理的 Skill 链接。",
                         epilog="示例: agentctl unlink --skill python-helper\n不指定 --skill 时处理当前环境启用的全部 Skill。",
                         formatter_class=argparse.RawDescriptionHelpFormatter)
    ulp.add_argument("--skill", action="append", metavar="NAME",
                     help="只处理指定 Skill；可重复传入")

    ep = sub.add_parser("export", help="制作可校验的离线工作区 ZIP",
                        description="收集工作区文件并扫描疑似 Secret，生成含清单与 SHA-256 校验的离线包。",
                        epilog="示例: agentctl export --with-wheels -o dist/workspace.zip\n默认输出到 dist/agent-workspace-v<版本>-offline.zip；本地 .env 和 local.yaml 不会入包。",
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    ep.add_argument("-o", "--output", default=None, metavar="ZIP", help="指定输出 ZIP 路径")
    ep.add_argument("--with-wheels", action="store_true",
                    help="调用 pip download，将 Python 依赖包加入 ZIP")
    ep.add_argument("--with-npm", action="store_true",
                    help="调用 npm pack，将 package.json 中的 Node 依赖包加入 ZIP")
    ep.add_argument("--dry-run", action="store_true", help="预览文件与依赖，不生成 ZIP 或下载依赖")

    ip = sub.add_parser("import", help="校验并导入离线工作区 ZIP",
                        description="校验离线包，备份当前工作区，再安装文件、刷新链接并运行 doctor。",
                        epilog="示例: agentctl import dist/workspace.zip --env intranet --dry-run\n设置本机环境时将 --env 放在 import 后；导入旧版本需显式使用 --force。",
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    ip.add_argument("bundle", metavar="ZIP", help="离线包路径，通常为 agent-workspace-vX.Y.Z-offline.zip")
    ip.add_argument("--env", dest="env", default=None, metavar="ENV", help="导入后设置的本机环境")
    ip.add_argument("--dry-run", action="store_true", help="校验并预览导入，不写入工作区")
    ip.add_argument("--force", action="store_true", help="允许导入比当前工作区更旧的版本")

    rp = sub.add_parser("restore", help="从导入前备份 ZIP 恢复工作区",
                        description="使用先前 import 创建的备份 ZIP 恢复工作区文件。",
                        epilog="示例: agentctl restore backups/<导入前备份>.zip\n此命令不用于恢复 adopt 产生的配置备份。",
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    rp.add_argument("backup", metavar="BACKUP_ZIP", help="先前 import 创建的 backups/ 下备份 ZIP 路径")

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
