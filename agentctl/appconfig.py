"""Application config capture and deploy (e.g. CopyQ).

App configs are declared in the ``app_configs:`` section of the layered
configs (common + profile + local.yaml). The declaration only describes
WHERE an app keeps its config and WHICH files belong to it:

    app_configs:
      copyq:
        description: CopyQ 剪贴板管理器
        target: "%APPDATA%/copyq"      # machine path, ~ and %VAR% expanded
        include:                       # glob patterns, relative to target
          - copyq.ini
          - copyq_tab_*.dat
        exclude:                       # matched relative paths to skip
          - "*.bak*"

Safety rules:
  - capture never touches git: output goes to user-data/ (gitignored) or
    an explicit --out; a manifest + SHA256SUMS make the result auditable
    and uploadable to a private channel.
  - deploy is backup-first: every file that already exists in the target
    is moved into backups/appconfig/<name>/<ts>/ before anything is
    written; the target directory is created if missing.
  - deploy from a ZIP validates entry names (no absolute paths, no "..")
    and only deploys files that match the declared include patterns.
  - if the app's process is (probably) running, capture and deploy warn:
    a live app may rewrite its files after we read or before we finish.
"""
from __future__ import annotations

import fnmatch
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from agentctl.utils import ensure_dir, now_ts, safe_zip_parts, shasum


class AppConfigError(RuntimeError):
    pass


@dataclass
class AppConfig:
    name: str
    description: str = ""
    target: Path = field(default_factory=Path)
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    process: str = ""


# ------------------------------------------------------------------ config

def _expand_path(raw: str) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(str(raw)))
    return Path(expanded)


def load_app_configs(root: Path, cfg) -> dict[str, AppConfig]:
    """Parse the app_configs section of an effective config."""
    section = cfg.raw.get("app_configs") or {}
    if not isinstance(section, dict):
        raise AppConfigError("app_configs: expected a mapping of name -> settings")
    apps: dict[str, AppConfig] = {}
    for name, spec in section.items():
        if not isinstance(spec, dict):
            raise AppConfigError(f"app_configs.{name}: expected a mapping")
        target_raw = spec.get("target")
        if not target_raw:
            raise AppConfigError(f"app_configs.{name}: missing 'target'")
        include = [str(p) for p in (spec.get("include") or [])]
        apps[str(name)] = AppConfig(
            name=str(name),
            description=str(spec.get("description") or ""),
            target=_expand_path(target_raw),
            include=include,
            exclude=[str(p) for p in (spec.get("exclude") or [])],
            process=str(spec.get("process") or ""),
        )
    return apps


def get_app(root: Path, cfg, name: str) -> AppConfig:
    apps = load_app_configs(root, cfg)
    if name not in apps:
        known = ", ".join(sorted(apps)) or "(none declared)"
        raise AppConfigError(f"unknown app config '{name}'; declared: {known}")
    return apps[name]


# ------------------------------------------------------------------ match

def _normalize(pattern: str) -> str:
    p = pattern.replace("\\", "/").lstrip("/")
    if p.endswith("/"):
        p += "*"
    return p


def _excluded(rel_posix: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel_posix, _normalize(p)) for p in patterns)


def match_files(target: Path, include: list[str], exclude: list[str]) -> list[Path]:
    """Existing files under target matching include and not exclude.

    Patterns are fnmatch globs against relative posix paths; a trailing
    '/' selects everything inside that directory.
    """
    if not include or not target.is_dir():
        return []
    all_files = [p for p in sorted(target.rglob("*")) if p.is_file()]
    out: list[Path] = []
    for p in all_files:
        rel = p.relative_to(target).as_posix()
        if not any(fnmatch.fnmatch(rel, _normalize(pat)) for pat in include):
            continue
        if _excluded(rel, exclude):
            continue
        out.append(p)
    return out


def process_running(process: str) -> bool | None:
    """Best-effort check whether the app's process is running.

    True / False when determinable, None when the check itself is
    unavailable on this platform.
    """
    if not process:
        return None
    if os.name == "nt":
        try:
            proc = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {process}", "/NH"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=15,
            )
            return process.lower() in (proc.stdout or "").lower()
        except (OSError, subprocess.TimeoutExpired):
            return None
    try:
        proc = subprocess.run(
            ["pgrep", "-x", Path(process).stem],
            capture_output=True, text=True, timeout=15,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return None


def warn_if_running(app: AppConfig) -> None:
    state = process_running(app.process)
    if state:
        print(f"WARN {app.process} 看起来正在运行：文件可能随时被应用改写。")
        print(f"     建议先退出 {app.name} 再执行本操作（尤其是 capture）。")


# ----------------------------------------------------------------- capture

def capture(app: AppConfig, out_dir: Path, dry_run: bool = False) -> list[Path]:
    """Copy the declared config files into out_dir (staging for private
    channels). Writes manifest.json + SHA256SUMS.txt alongside."""
    files = match_files(app.target, app.include, app.exclude)
    if not files:
        raise AppConfigError(
            f"no files matched under {app.target} for app '{app.name}' "
            f"(include: {app.include}) - is the app installed and configured?"
        )
    plan = [(f, f.relative_to(app.target)) for f in files]
    if dry_run:
        print(f"[dry-run] would copy {len(plan)} file(s) "
              f"{app.target} -> {out_dir}:")
        for src, rel in plan[:30]:
            print(f"  {rel.as_posix()}  ({src.stat().st_size} bytes)")
        return [src for src, _ in plan]

    ensure_dir(out_dir)
    for src, rel in plan:
        dest = out_dir.joinpath(*rel.parts)
        ensure_dir(dest.parent)
        shutil.copy2(src, dest)

    manifest = {
        "app": app.name,
        "description": app.description,
        "source_target": str(app.target),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "file_count": len(plan),
        "total_bytes": sum(src.stat().st_size for src, _ in plan),
        "files": [
            {"path": rel.as_posix(), "size": src.stat().st_size}
            for src, rel in plan
        ],
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    sums = [(shasum(out_dir / rel), rel.as_posix()) for _, rel in plan]
    (out_dir / "SHA256SUMS.txt").write_text(
        "".join(f"{h}  {n}\n" for h, n in sums), encoding="utf-8")

    print(f"Captured {len(plan)} file(s) -> {out_dir}")
    for _, rel in plan:
        print(f"  {rel.as_posix()}")
    print(f"  manifest.json + SHA256SUMS.txt written")
    return [src for src, _ in plan]


def zip_capture(out_dir: Path, dry_run: bool = False) -> Path:
    """Zip a capture directory next to itself; return the ZIP path."""
    if not out_dir.is_dir():
        raise AppConfigError(f"capture directory not found: {out_dir}")
    zip_path = out_dir.with_suffix(".zip")
    if dry_run:
        print(f"[dry-run] would write {zip_path} + SHA256SUMS.txt")
        return zip_path
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(out_dir.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(out_dir.parent).as_posix())
    sums = f"{shasum(zip_path)}  {zip_path.name}\n"
    (out_dir.parent / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")
    print(f"ZIP   {zip_path}  ({zip_path.stat().st_size} bytes)")
    print(f"SHA-256 {shasum(zip_path)}")
    return zip_path


# ------------------------------------------------------------------ deploy

def _payload_root(extract_dir: Path, names: list[str]) -> Path:
    """Pick the directory inside a ZIP that holds the config files:
    a single top-level directory if present, else the extract root."""
    tops = {n.replace("\\", "/").split("/")[0] for n in names}
    if len(tops) == 1:
        candidate = extract_dir / tops.pop()
        if candidate.is_dir():
            return candidate
    return extract_dir


def _plan_from_dir(src: Path, app: AppConfig) -> list[tuple[Path, str]]:
    files = match_files(src, app.include, app.exclude)
    return [(f, f.relative_to(src).as_posix()) for f in files]


def _plan_from_zip(src: Path, app: AppConfig, extract_dir: Path) -> list[tuple[Path, str]]:
    with zipfile.ZipFile(src) as zf:
        names = zf.namelist()
        for n in names:
            if safe_zip_parts(n) is None:
                raise AppConfigError(f"unsafe path in ZIP: {n}")
        zf.extractall(extract_dir)
    base = _payload_root(extract_dir, names)
    files = match_files(base, app.include, app.exclude)
    return [(f, f.relative_to(base).as_posix()) for f in files]


def deploy(app: AppConfig, source: Path, root: Path,
           dry_run: bool = False) -> int:
    """Deploy declared config files from a directory or ZIP into the
    app's target directory. Existing files are backed up first."""
    source = Path(source).expanduser()
    if not source.exists():
        raise AppConfigError(f"source not found: {source}")
    staged: Path | None = None
    try:
        if source.is_dir():
            pairs = _plan_from_dir(source, app)
        elif source.suffix.lower() == ".zip":
            staged = Path(tempfile.mkdtemp(prefix="agentctl-appconfig-"))
            pairs = _plan_from_zip(source, app, staged)
        else:
            raise AppConfigError(f"unsupported source (need dir or .zip): {source}")

        if not pairs:
            raise AppConfigError(
                f"no files matching app '{app.name}' patterns {app.include} in {source}"
            )
        target = app.target
        exists = [(s, r) for s, r in pairs if (target / r).exists()]
        fresh = [(s, r) for s, r in pairs if not (target / r).exists()]

        print(f"Source  {source}")
        print(f"Target  {target}")
        print(f"Plan    {len(pairs)} file(s): {len(exists)} replace "
              f"(backup first), {len(fresh)} new")
        for s, r in pairs[:30]:
            tag = "replace" if (target / r).exists() else "new"
            print(f"  [{tag}] {r}  ({s.stat().st_size} bytes)")
        if dry_run:
            print("[dry-run] no files were changed")
            return 0

        warn_if_running(app)

        if exists:
            backup_dir = root / "backups" / "appconfig" / app.name / now_ts()
            ensure_dir(backup_dir)
            for _, rel in exists:
                dest = backup_dir.joinpath(*Path(rel).parts)
                ensure_dir(dest.parent)
                shutil.move(str(target / rel), str(dest))
            print(f"Backup  {len(exists)} replaced file(s) -> {backup_dir}")

        for s, rel in pairs:
            dest = target / rel
            ensure_dir(dest.parent)
            shutil.copy2(s, dest)
        print(f"Deployed {len(pairs)} file(s) -> {target}")
        print(f"Next: restart {app.name} if it was running, then verify it loads "
              f"the restored config.")
        return 0
    finally:
        if staged is not None:
            shutil.rmtree(staged, ignore_errors=True)


# ------------------------------------------------------------------ status

def status(app: AppConfig) -> int:
    """Compare declared patterns against the live target directory."""
    print(f"{app.name}  ->  {app.target}")
    if app.description:
        print(f"  {app.description}")
    if not app.target.is_dir():
        print("  FAIL target directory does not exist (app not installed?)")
        return 1
    files = match_files(app.target, app.include, app.exclude)
    if not files:
        print(f"  FAIL no declared files found (include: {app.include})")
        return 1
    total = 0
    for f in files:
        rel = f.relative_to(app.target).as_posix()
        print(f"  ok   {rel}  ({f.stat().st_size} bytes)")
        total += 1
    print(f"  {total} declared file(s) present")
    return 0


def list_apps(apps: dict[str, AppConfig]) -> int:
    if not apps:
        print("no app_configs declared (see configs/common.yaml)")
        return 0
    for name, app in apps.items():
        print(f"{name}  ->  {app.target}")
        if app.description:
            print(f"  {app.description}")
    return 0


# --------------------------------------------------------------------- run

def run(root: Path, cfg, args) -> int:
    action = args.appconfig_command
    if action == "list":
        return list_apps(load_app_configs(root, cfg))
    if action == "status":
        apps = load_app_configs(root, cfg)
        if getattr(args, "name", None):
            return status(get_app(root, cfg, args.name))
        rc = 0
        for name in sorted(apps):
            if status(apps[name]) != 0:
                rc = 1
        return rc
    if action == "capture":
        app = get_app(root, cfg, args.name)
        warn_if_running(app)
        out = (Path(args.out).expanduser() if args.out
               else root / "user-data" / app.name)
        capture(app, out, dry_run=args.dry_run)
        if args.zip:
            zip_capture(out, dry_run=args.dry_run)
        return 0
    if action == "deploy":
        app = get_app(root, cfg, args.name)
        return deploy(app, args.from_src, root, dry_run=args.dry_run)
    raise AppConfigError(f"unknown appconfig action: {action}")
