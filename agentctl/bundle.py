"""Offline bundle export / import.

Bundle layout (zip):
  workspace/...        the workspace files (git-tracked when possible)
  wheels/...           optional python wheels   (--with-wheels)
  npm/...              optional npm tarballs     (--with-npm)
  manifest.json        metadata
  VERSION              release version (duplicate of workspace/VERSION)
  SHA256SUMS           sha256 of every other file in the bundle

Safety rules:
  - .env / local.yaml / backups / dist / packages / manifests never enter
    a bundle, regardless of how the file list was collected
  - every exported text file is scanned for secret-looking content and
    export refuses to continue on a hit (reports file:line, never the value)
  - import verifies SHA256SUMS before touching anything and refuses
    bundles that contain .env / local.yaml or unsafe paths
  - import backs up the current workspace first; failures during the write
    phase roll back automatically
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from agentctl import environment as env_mod
from agentctl import gitops, workspace
from agentctl.config import build_effective
from agentctl.doctor import print_checks, run_checks
from agentctl.links import LinkManager
from agentctl.utils import now_ts, safe_zip_parts, shasum

DENY_NAMES = {".env", "local.yaml"}
DENY_DIRS = {".git", ".venv", "__pycache__", "backups", "dist", "packages",
             "manifests", "node_modules", ".pytest_cache", ".hatch"}
DENY_SUFFIXES = (".pyc", ".pyo", ".zip", ".egg-info")

SECRET_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "OpenAI-style API key"),
    (re.compile(r"ghp_[A-Za-z0-9]{30,}"), "GitHub token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "GitHub fine-grained token"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
]


class BundleError(RuntimeError):
    pass


# ------------------------------------------------------------------ collect

def _denied(parts: list[str]) -> bool:
    if parts[-1] in DENY_NAMES:
        return True
    if any(p in DENY_DIRS for p in parts):
        return True
    return parts[-1].endswith(DENY_SUFFIXES)


def collect_files(root: Path) -> tuple[list[Path], str]:
    """Files that go into the bundle. Returns (paths, mode).

    mode is "git" (tracked files, respects .gitignore) or "walk"
    (manual exclusion rules, for workspaces not yet under git).
    """
    if gitops.available() and gitops.is_repo(root) and gitops.has_commits(root):
        rels = [p for p in gitops.tracked_files(root) if not _denied(p.split("/"))]
        return [root / r for r in rels], "git"
    rels: list[str] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if _denied(list(rel.parts)):
            continue
        rels.append(rel.as_posix())
    return [root / r for r in rels], "walk"


def scan_secrets(files: list[Path], root: Path) -> list[str]:
    """Return 'file:line looks like a <label>' strings. Never the value."""
    problems: list[str] = []
    for f in files:
        try:
            if f.stat().st_size > 1_000_000:
                continue
            with open(f, "rb") as fh:
                head = fh.read(8192)
            if b"\x00" in head:
                continue  # binary
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for rx, label in SECRET_PATTERNS:
                if rx.search(line):
                    rel = f.relative_to(root).as_posix()
                    problems.append(f"{rel}:{i} looks like a {label}")
                    break
    return problems


def _node_deps(root: Path) -> list[str]:
    pj = root / "package.json"
    if not pj.is_file():
        return []
    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    out: list[str] = []
    for section in ("dependencies", "devDependencies"):
        for name, ver in (data.get(section) or {}).items():
            out.append(f"{name}@{ver}")
    return out


def _pip_cmd() -> list[str] | None:
    for prefix in ([sys.executable, "-m", "pip"], ["pip"], ["python", "-m", "pip"]):
        try:
            proc = subprocess.run(
                prefix + ["--version"], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=60,
            )
            if proc.returncode == 0:
                return prefix
        except (OSError, subprocess.TimeoutExpired):
            continue
    return None


def _pip_download(deps: list[str], dest: Path) -> None:
    pip = _pip_cmd()
    if not pip:
        raise BundleError(
            "pip is not usable for wheel download; "
            "install pip or export without --with-wheels"
        )
    proc = subprocess.run(
        pip + ["download", "-d", str(dest), "--quiet", *deps],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise BundleError(
            "pip download failed:\n" + (proc.stderr or proc.stdout).strip()[:500]
        )


def _npm_pack(deps: list[str], dest: Path) -> None:
    if shutil.which("npm") is None:
        raise BundleError("npm not found; export without --with-npm")
    for spec in deps:
        proc = subprocess.run(
            ["npm", "pack", spec, "--pack-destination", str(dest)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if proc.returncode != 0:
            raise BundleError(f"npm pack {spec} failed:\n" + (proc.stderr or "").strip()[:300])


def parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except ValueError:
        return (0,)


def _cmp_versions(a: str, b: str) -> int:
    pa, pb = parse_version(a), parse_version(b)
    return (pa > pb) - (pa < pb)


# ------------------------------------------------------------------- export

def export_bundle(root: Path, output: str | None = None, with_wheels: bool = False,
                  with_npm: bool = False, dry_run: bool = False) -> Path:
    version = workspace.read_version(root)
    files, mode = collect_files(root)
    if not files:
        raise BundleError("No files found to export (empty workspace?)")

    problems = scan_secrets(files, root)
    if problems:
        raise BundleError(
            "Refusing to export: possible secrets detected "
            "(locations only, never values):\n  " + "\n  ".join(problems)
        )

    commit = None
    if gitops.available() and gitops.is_repo(root):
        commit = gitops.current_commit(root)
    out = (Path(output).expanduser() if output
           else root / "dist" / f"agent-workspace-v{version}-offline.zip")
    deps = workspace.python_dependencies(root)
    npm_deps = _node_deps(root)

    if dry_run:
        print(f"[dry-run] mode={mode} files={len(files)} version=v{version} "
              f"commit={(commit or 'none')[:12]}")
        print(f"[dry-run] wheels: {'pip download ' + ', '.join(deps) if with_wheels else 'none'}")
        if with_npm:
            note = "npm pack " + ", ".join(npm_deps) if npm_deps else "skipped (no package.json)"
            print(f"[dry-run] npm: {note}")
        print(f"[dry-run] output: {out}")
        for f in files[:30]:
            print(f"  {f.relative_to(root).as_posix()}")
        if len(files) > 30:
            print(f"  ... and {len(files) - 30} more")
        return out

    if mode == "git" and gitops.is_dirty(root):
        print("WARN workspace has uncommitted changes; they are NOT in the bundle.")
        print("     commit first for a reproducible release.")

    dist = root / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="agentctl-export-", dir=str(dist)))
    try:
        ws_dir = staging / "workspace"
        for f in files:
            dest = ws_dir.joinpath(*f.relative_to(root).parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)

        if with_wheels:
            _pip_download(deps, staging / "wheels")
        if with_npm and npm_deps:
            _npm_pack(npm_deps, staging / "npm")
        elif with_npm:
            print("note: --with-npm given but no package.json dependencies; skipped")

        manifest = {
            "version": version,
            "git_commit": commit,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "export_mode": mode,
            "skills": sorted(p.name for p in (root / "skills").iterdir() if p.is_dir())
                      if (root / "skills").is_dir() else [],
            "agents": sorted(p.name for p in (root / "agents").iterdir() if p.is_dir())
                      if (root / "agents").is_dir() else [],
            "python_packages": deps,
            "node_packages": npm_deps,
            "file_count": len(files),
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        (staging / "VERSION").write_text(version + "\n", encoding="utf-8")

        # SHA256SUMS over every file written so far (itself excluded)
        sums = []
        for p in sorted(staging.rglob("*")):
            if p.is_file():
                sums.append((shasum(p), p.relative_to(staging).as_posix()))
        (staging / "SHA256SUMS").write_text(
            "".join(f"{h}  {n}\n" for h, n in sums), encoding="utf-8")

        if out.exists():
            out.unlink()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(staging.rglob("*")):
                if p.is_file():
                    zf.write(p, p.relative_to(staging).as_posix())

        mdir = root / "manifests"
        mdir.mkdir(parents=True, exist_ok=True)
        (mdir / f"{out.stem}.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    print(f"Exported {out}")
    print(f"  version v{version}, {len(files)} workspace files, "
          f"commit {(commit or 'none')[:12]}")
    if with_wheels:
        print("  python wheels included")
    if with_npm and npm_deps:
        print("  npm tarballs included")
    return out


# ------------------------------------------------------------------- verify

def read_manifest_and_verify(bundle_path: Path) -> dict:
    if not bundle_path.is_file():
        raise BundleError(f"Bundle not found: {bundle_path}")
    errors: list[str] = []
    with zipfile.ZipFile(bundle_path) as zf:
        names = zf.namelist()
        for n in names:
            if any(p in DENY_NAMES for p in n.replace("\\", "/").split("/")):
                raise BundleError(f"Bundle contains forbidden local-state file: {n}")
        if "manifest.json" not in names:
            raise BundleError("Bundle is missing manifest.json")
        if "SHA256SUMS" not in names:
            raise BundleError("Bundle is missing SHA256SUMS")
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        for line in zf.read("SHA256SUMS").decode("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            digest, _, name = line.partition("  ")
            name = name.strip()
            if name not in names:
                errors.append(f"SHA256SUMS lists missing entry: {name}")
                continue
            actual = hashlib.sha256(zf.read(name)).hexdigest()
            if actual != digest:
                errors.append(f"checksum mismatch: {name}")
    if errors:
        raise BundleError(
            "Bundle verification failed (corrupted or tampered):\n  "
            + "\n  ".join(errors)
        )
    return manifest


# ------------------------------------------------------------------- import

def _extract_bundle(root: Path, bundle_path: Path) -> None:
    with zipfile.ZipFile(bundle_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            parts = safe_zip_parts(info.filename)
            if parts is None:
                raise BundleError(f"Unsafe path in bundle: {info.filename}")
            if any(p in DENY_NAMES for p in parts):
                raise BundleError(f"Bundle contains forbidden file: {info.filename}")
            top = parts[0]
            rest = parts[1:]
            if top == "workspace" and rest:
                dest = root.joinpath(*rest)
            elif top == "wheels" and rest:
                dest = (root / "packages" / "wheels").joinpath(*rest)
            elif top == "npm" and rest:
                dest = (root / "packages" / "npm").joinpath(*rest)
            elif "/".join(parts) in ("manifest.json", "VERSION", "SHA256SUMS"):
                continue
            else:
                print(f"note: skipping unrecognized bundle entry {info.filename}")
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(info))


def _restore_zip(root: Path, backup_zip: Path) -> None:
    with zipfile.ZipFile(backup_zip) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            parts = safe_zip_parts(info.filename)
            if parts is None:
                raise BundleError(f"Unsafe path in backup: {info.filename}")
            dest = root.joinpath(*parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(info))


def _backup_current(root: Path, current_version: str) -> Path | None:
    files, _ = collect_files(root)
    if not files:
        return None
    backup = root / "backups" / f"workspace-v{current_version}-{now_ts()}.zip"
    backup.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(backup, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(files):
            zf.write(f, f.relative_to(root).as_posix())
    return backup


def import_bundle(root: Path, bundle_path: str | Path, environment: str | None = None,
                  dry_run: bool = False, force: bool = False) -> int:
    bundle_path = Path(bundle_path).expanduser()
    manifest = read_manifest_and_verify(bundle_path)
    bver = str(manifest.get("version") or "?")
    cur = workspace.read_version(root) if (root / "VERSION").is_file() else "0.0.0"

    print(f"Bundle   v{bver} ({manifest.get('file_count', '?')} files, "
          f"commit {str(manifest.get('git_commit') or 'none')[:12]})")
    print(f"Current  v{cur}")
    if _cmp_versions(bver, cur) < 0 and not force:
        print(f"FAIL bundle is OLDER than the current workspace (v{bver} < v{cur}).")
        print("     Pass --force if you really want to downgrade.")
        return 1
    if _cmp_versions(bver, cur) == 0:
        print("note: same version; refreshing files")

    with zipfile.ZipFile(bundle_path) as zf:
        names = [n.replace("\\", "/") for n in zf.namelist()]
        ws_members = [n for n in names if n.startswith("workspace/")]
        wheels_members = [n for n in names if n.startswith("wheels/")]
        touched = sorted({n.split("/")[1] for n in ws_members if len(n.split("/")) > 2})
    print(f"Plan: extract {len(ws_members)} files (top-level: {', '.join(touched) or 'none'})")
    if wheels_members:
        print(f"      {len(wheels_members)} wheel(s) -> packages/wheels "
              f"(used by offline bootstrap)")
    if environment:
        print(f"      set environment to '{environment}'")

    if dry_run:
        print("[dry-run] would: backup current workspace -> backups/, extract, "
              "re-link skills, run doctor")
        return 0

    backup = _backup_current(root, cur)
    if backup:
        print(f"Backup   {backup.relative_to(root).as_posix()}")

    try:
        _extract_bundle(root, bundle_path)
        if environment:
            env_mod.set_environment(root, environment)
        mdir = root / "manifests"
        mdir.mkdir(parents=True, exist_ok=True)
        (mdir / f"{bundle_path.stem}.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    except Exception as e:
        if backup:
            print(f"FAIL import failed: {e}")
            print("Rolling back ...")
            _restore_zip(root, backup)
            print(f"Rolled back to previous state ({backup.name})")
        raise BundleError(f"import failed: {e}") from e

    # re-link + doctor
    try:
        env_now, _ = env_mod.resolve(root)
    except env_mod.EnvError:
        env_now = None
    cfg = build_effective(root, env_now)
    lm = LinkManager.from_config(root, cfg)
    for line in lm.apply(lm.plan(cfg.enabled_skills)):
        print(line)

    print()
    print("Running doctor ...")
    rc = print_checks(run_checks(root))
    if rc != 0 and backup:
        print()
        print("Doctor reported failures. The import itself completed and verified;")
        print(f"roll back manually anytime with: agentctl restore backups/{backup.name}")
    return rc


def restore_backup(root: Path, backup_zip: str | Path) -> int:
    p = Path(backup_zip).expanduser()
    if not p.is_file():
        raise BundleError(f"Backup not found: {p}")
    _restore_zip(root, p)
    print(f"Restored workspace files from {p.name}")
    print("Next: agentctl link   (refresh skill links)")
    print("      agentctl doctor (verify)")
    return 0