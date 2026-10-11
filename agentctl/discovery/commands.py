"""CLI orchestration and a single sanitized output boundary."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agentctl import config
from . import providers, storage
from .compare import compare, exit_code, summary
from .model import DiscoveryError, declarations, provider_name, resource_id, safe_text

COMMANDS = {"scan", "diff", "snapshot", "adopt", "ignore"}


def add_parsers(sub):
    details = {
        "scan": (
            "查询本机已安装资源，并与有效配置比较；不写入状态或配置。",
            "示例: agentctl scan --full --new\n默认 quick 扫描 uv、pipx、npm、pnpm、vscode；--full 另含 winget。",
        ),
        "diff": (
            "比较本机资源与有效配置中的 resources 声明；不写入状态或配置。",
            "示例: agentctl --env personal diff --full --check\n默认隐藏 MATCH 项；--all 可显示所有比较结果。",
        ),
        "snapshot": (
            "完整扫描六个 Provider，并保存最近一次发现基线用于后续历史比较。",
            "示例: agentctl snapshot --dry-run\n任一 Provider 报 error 时保留旧基线；unavailable 可保存为未覆盖。",
        ),
        "adopt": (
            "把已发现且来源明确的资源登记到指定共享 profile；不会安装软件。",
            "示例: agentctl adopt npm:example --profile personal --dry-run\n只传 --profile 可列候选；指定 ID 或 --all 才写入。--profile 不能是 local。",
        ),
        "ignore": (
            "管理本机的精确资源忽略项，仅隐藏未登记提醒。",
            "示例: agentctl ignore npm:example\n查看: agentctl ignore --list；移除: agentctl ignore npm:example --remove。",
        ),
    }
    for name in ("scan", "diff", "snapshot", "adopt", "ignore"):
        parser = sub.add_parser(name, help=details[name][0], description=details[name][0],
                                epilog=details[name][1],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
        parser.add_argument("--json", action="store_true", help="输出单个 JSON 对象，适合脚本读取")
        if name != "snapshot":
            parser.add_argument("--provider", choices=list(providers.PROVIDERS), metavar="PROVIDER",
                                help="限定资源所属 Provider；可选 " + ", ".join(providers.PROVIDERS))
        if name in {"scan", "diff"}:
            mode = parser.add_mutually_exclusive_group()
            mode.add_argument("--quick", action="store_true",
                              help="快速扫描五个 Provider（默认，不含 winget）")
            mode.add_argument("--full", action="store_true", help="完整扫描六个 Provider（含 winget）")
            parser.add_argument("--all", action="store_true", help="包含被忽略项；diff 也显示 MATCH 项")
            parser.add_argument("--check", action="store_true",
                                help="发现 DRIFT/MISSING 返回 1；声明资源证据不足返回 2")
        if name == "scan":
            parser.add_argument("--new", action="store_true", help="只显示未登记且未忽略的资源")
        if name in {"adopt", "ignore"}:
            parser.add_argument("resources", nargs="*", metavar="[PROVIDER:]ID",
                                help="资源身份，如 npm:example；使用 --provider 时可省略前缀")
        if name == "adopt":
            parser.add_argument("--profile", required=True, metavar="PROFILE",
                                help="写入的共享配置层，如 common、personal、company、intranet")
            parser.add_argument("--all", action="store_true", help="登记扫描范围内所有合格候选；不能同时指定 ID")
            parser.add_argument("--pin-version", action="store_true",
                                help="登记时锁定当前版本；版本未知则拒绝写入")
        if name == "ignore":
            mode = parser.add_mutually_exclusive_group()
            mode.add_argument("--list", action="store_true", help="列出本机忽略项")
            mode.add_argument("--remove", action="store_true", help="从本机忽略项移除指定资源")
        if name in {"snapshot", "adopt", "ignore"}:
            parser.add_argument("--dry-run", action="store_true", help="预览结果，不写入状态或配置")


def identities(args) -> set[tuple[str, str]]:
    result = set()
    for value in args.resources:
        if ":" in value:
            provider, name = value.split(":", 1)
            if args.provider and args.provider != provider:
                raise DiscoveryError("provider-conflict")
        elif args.provider:
            provider, name = args.provider, value
        else:
            raise DiscoveryError("provider-required")
        if provider not in providers.PROVIDERS:
            raise DiscoveryError("unknown-provider")
        result.add((provider_name(provider), resource_id(provider, name)))
    return result


def environment(root: Path, override: str | None) -> str | None:
    local = storage.load_yaml(storage.read_bytes(root / "local.yaml"))
    name = override or os.environ.get("AGENTCTL_ENV") or local.get("environment")
    if name is not None:
        safe_text(name, r"[A-Za-z0-9_-]+", 80)
        if name == "local" or not config.profile_path(root, name).is_file():
            raise DiscoveryError("unknown-environment")
    return name


def emit(data: dict, json_mode: bool):
    if json_mode:
        print(json.dumps(data, ensure_ascii=True, sort_keys=True))
        return
    if "error" in data:
        print(f"ERROR: {data['error']}", file=sys.stderr)
        return
    if data.get("dry_run"):
        print("[dry-run] no files written")
    for provider in data.get("providers", []):
        print(f"{provider['provider']}: {provider['status']}" +
              (f" ({provider['error']})" if provider.get("error") else ""))
    for row in data.get("resources", []):
        print(f"{row['status']:13} {row['provider']}:{row['id']} "
              f"observed={row['observed_version'] or '?'} desired={row['desired_version'] or '*'} "
              f"{row['history']}" + (" [ignored]" if row["ignored"] else ""))
    for field in ("candidates", "adopted", "ignored", "local_overrides"):
        for row in data.get(field, []):
            extra = f" effective_version={row['effective_version'] or '*'}" if field == "local_overrides" else ""
            print(f"{field}: {row['provider']}:{row['id']}{extra}")
    if "summary" in data:
        print("summary: " + json.dumps(data["summary"], sort_keys=True))
    if "saved" in data:
        print("snapshot: " + ("saved" if data["saved"] else "not saved"))


def execute(root: Path, args) -> tuple[dict, int]:
    if args.command == "ignore":
        keys = identities(args)
        if args.list and keys:
            raise DiscoveryError("invalid-ignore-arguments")
        expected = storage.read_bytes(storage.ignore_path(root))
        ignored = storage.load_ignore(root)
        if keys:
            ignored = ignored - keys if args.remove else ignored | keys
            storage.save_ignore(root, ignored, expected, args.dry_run)
        elif args.remove:
            raise DiscoveryError("resource-required")
        return {"schema_version": 1, "ignored": [{"provider": p, "id": i} for p, i in sorted(ignored)],
                "dry_run": args.dry_run}, 0

    env = environment(root, args.env_global)
    desired = declarations(config.build_effective(root, env).raw)
    ignored = storage.load_ignore(root)
    previous_bytes = storage.read_bytes(storage.snapshot_path(root))
    previous = storage.load_snapshot(root)
    keys = identities(args) if args.command == "adopt" else set()
    if getattr(args, "provider", None):
        names = [args.provider]
    elif args.command == "snapshot" or getattr(args, "full", False):
        names = list(providers.PROVIDERS)
    elif keys:
        names = sorted({p for p, _ in keys})
    else:
        names = list(providers.PROVIDERS) if args.command == "adopt" else list(providers.QUICK)
    results = providers.scan(names, root)
    # --provider narrows the comparison. Quick retains unscanned declarations
    # as INDETERMINATE so --check cannot silently pass them.
    if getattr(args, "provider", None):
        desired = {key: value for key, value in desired.items() if key[0] == args.provider}
        previous = [r for r in previous or [] if r.provider == args.provider] if previous is not None else None
    rows = compare(desired, results, previous, ignored)
    data = {"schema_version": 1, "environment": env,
            "providers": [{k: v for k, v in r.to_dict().items() if k != "resources"} for r in results],
            "resources": rows, "summary": summary(rows)}
    code = exit_code(results, rows, getattr(args, "check", False))
    if args.command == "snapshot":
        data.update(saved=False, dry_run=args.dry_run)
        if code == 0:
            storage.save_snapshot(root, results, previous_bytes, args.dry_run)
            data["saved"] = not args.dry_run
    elif args.command == "adopt":
        safe_text(args.profile, r"[A-Za-z0-9_-]+", 80)
        if args.profile == "local" or not config.profile_path(root, args.profile).is_file():
            raise DiscoveryError("unknown-profile")
        shared = config._load_yaml(config.profile_path(root, "common"))
        if args.profile != "common":
            shared = config.merge(shared, config._load_yaml(config.profile_path(root, args.profile)))
        existing = declarations(shared)
        found = {r.key: r for p in results for r in p.resources}
        candidates = [r for k, r in found.items() if k not in existing and k not in ignored and r.source != "unknown"]
        data["candidates"] = [r.to_dict() for r in candidates]
        if args.all and keys:
            raise DiscoveryError("choose-resource-or-all")
        if args.all or keys:
            if code or any(k not in found and k not in existing for k in keys):
                raise DiscoveryError("adopt-discovery-incomplete")
            selected = candidates if args.all else [found[k] for k in sorted(keys) if k not in existing]
            data.update(storage.adopt(root, args.profile, selected, args.pin_version, args.dry_run))
    else:
        if getattr(args, "new", False):
            data["resources"] = [r for r in rows if not r["declared"] and not r["ignored"] and r["status"] in {"NEW", "UNKNOWN"}]
        elif not args.all:
            data["resources"] = [r for r in rows if not r["ignored"] and not (args.command == "diff" and r["status"] == "MATCH")]
    return data, code


def run(root: Path, args) -> int:
    try:
        data, code = execute(root, args)
    except Exception as exc:
        # Includes YAML parser errors, invalid external structures and OS errors.
        # Never forward exception text, raw stdout/stderr, or config fragments.
        category = str(exc) if isinstance(exc, DiscoveryError) else "configuration-or-state-error"
        data, code = {"schema_version": 1, "error": category}, 2
    emit(data, args.json)
    return code
