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
    a bundle, regardless of how the file list was collected; the deny list
    mirrors .gitignore (user-data, work, .agent-teams, .uv-cache, *.7z, ...)
    and applies to both the git and the walk collection mode
  - collection never follows symlinked directories (Python <= 3.12 rglob
    would walk out of the workspace); symlinked files are skipped too
  - DENY_PREFIXES paths are outside the bundle scope entirely (never
    collected, never secret-scanned); import refuses bundle entries
    under them so the local copy stays authoritative
  - every exported text file is scanned for secret-looking content and
    export refuses to continue on a hit (reports file:line, never the
    value); large files are streamed and scanned like everything else,
    and the canary marker only exempts the known canary samples
  - import verifies SHA256SUMS before touching anything: the zip contents
    must equal the sums list (unlisted and missing entries are both
    refused, so extra files cannot be smuggled past the checksums), and
    entries under excluded directories (.git/ ...) are refused in depth
  - import backs up the current workspace first; failures during extract,
    environment switch, re-link or doctor roll back automatically,
    including removing files the import had created
"""
from __future__ import annotations

import hashlib
import json
import os
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
from agentctl.links import COPY_MARKER, LinkError, LinkManager, remove_managed
from agentctl.utils import now_ts, safe_zip_parts, shasum

DENY_NAMES = {".env", "local.yaml", "Thumbs.db", ".DS_Store"}
DENY_DIRS = {".git", ".venv", "__pycache__", "backups", "dist", "packages",
             "manifests", "node_modules", ".pytest_cache", ".hatch", ".agentctl",
             "user-data", "work", ".agent-teams", ".uv-cache"}
DENY_SUFFIXES = (".pyc", ".pyo", ".pyd", ".zip", ".7z", ".egg-info")

# Relative-POSIX path prefixes (workspace-root anchored) that sit outside
# the bundle scope entirely. Used for content that is legitimately tracked
# in git but must never ship offline:
#   - projects/cloudmusic-r: the CloudMusic_R reverse-engineering workspace
#     trips the private-key scan with vendor JS chunks and is of no use on
#     intranet machines
#   - projects/xerj: upstream reference clone (.gitignore: local sync only)
# Deliberate hard-coded list, auditable in git, kept in sync with
# .gitignore; import refuses bundle entries under these prefixes instead of
# silently overwriting the local copy.
DENY_PREFIXES = ("projects/cloudmusic-r/", "projects/xerj/")

# A line carrying this marker is scanned as usual; only pattern matches that
# ARE one of the known canary samples below are exempt on such a line. A
# real secret cannot hide behind the marker: any other match on the same
# line is still reported. Auditable: grep for the marker and the samples
# (the registry lines below carry the marker themselves).
CANARY_MARKER = "# agentctl-canary"
CANARY_SAMPLES = (
    "sk-abcdefghijklmnopqrstuvwx",        # agentctl-canary
    "sk-proj-q1w2e3r4t5y6u7i8o9p0z1x2",   # agentctl-canary
    "sk-ant-api03-q1w2e3r4t5y6u7i8o9p0z1x2",  # agentctl-canary
    "sk-or-v1-q1w2e3r4t5y6u7i8o9p0z1x2",  # agentctl-canary
    "-----BEGIN RSA PRIVATE KEY-----",    # agentctl-canary
)

# Files above this size are still scanned (streaming, bounded memory); the
# size only controls the visibility warning. Nothing is skipped silently.
LARGE_FILE_WARN_BYTES = 1_000_000

SECRET_PATTERNS = [
    # 'sk-' must start a standalone token (not sit inside a hyphenated word
    # like 'task-based-...'), may carry up to two short alnum prefix
    # segments (sk-proj-, sk-ant-api03-, sk-or-v1-), then needs a 20+ char
    # alphanumeric body. Keeps real keys detectable while ignoring URL
    # slugs such as 'task-based-asynchronous-programming'.
    (re.compile(r"(?<![A-Za-z0-9_-])sk-(?:[A-Za-z0-9]{1,16}-){0,2}[A-Za-z0-9]{20,}"),
     "OpenAI-style API key"),
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
    # name-based deny lists apply to every path segment (a file inside a
    # denied directory is denied), suffixes also match directory segments
    # so e.g. *.egg-info/ trees are excluded as a whole, like .gitignore
    for p in parts:
        if p in DENY_DIRS or p.endswith(DENY_SUFFIXES):
            return True
    return parts[-1] in DENY_NAMES


def _denied_prefix(parts: list[str]) -> bool:
    rel = "/".join(parts)
    return any(rel.startswith(prefix) for prefix in DENY_PREFIXES)


def _walk_files(root: Path) -> list[Path]:
    """Regular files under root, never leaving the tree.

    pathlib rglob("*/**") on Python <= 3.12 follows symlinked directories,
    which can pull files from outside the workspace into the bundle. Use
    os.walk(followlinks=False) with explicit pruning; symlinked files are
    skipped as well because copying them would follow the link outside.
    """
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames
                             if not (Path(dirpath) / d).is_symlink())
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            if p.is_symlink() or not p.is_file():
                continue
            out.append(p)
    return out


def collect_files(root: Path) -> tuple[list[Path], str]:
    """Files that go into the bundle. Returns (paths, mode).

    mode is "git" (tracked files, respects .gitignore) or "walk"
    (manual exclusion rules, for workspaces not yet under git).
    """
    if gitops.available() and gitops.is_repo(root) and gitops.has_commits(root):
        rels = [p for p in gitops.tracked_files(root)
                if not _denied(p.split("/")) and not _denied_prefix(p.split("/"))]
        return [root / r for r in rels], "git"
    rels: list[str] = []
    for p in sorted(_walk_files(root)):
        rel = p.relative_to(root)
        if _denied(list(rel.parts)) or _denied_prefix(list(rel.parts)):
            continue
        rels.append(rel.as_posix())
    return [root / r for r in rels], "walk"


def _iter_text_lines(path: Path):
    """Yield decoded text lines with bounded memory.

    Binary files (NUL in the first 8 KiB) yield nothing. Unlike the old
    size-based skip, every text file is scanned, streamed in chunks so a
    multi-megabyte file cannot blow up memory. A single line longer than
    the window is still scanned in window-sized pieces.
    """
    window = 1 << 20
    max_line_buf = 8 << 20
    with open(path, "rb") as fh:
        if b"\x00" in fh.read(8192):
            return
        fh.seek(0)
        buf = b""
        for chunk in iter(lambda: fh.read(window), b""):
            buf += chunk
            lines = buf.split(b"\n")
            buf = lines.pop()
            for ln in lines:
                yield ln.decode("utf-8", errors="replace").rstrip("\r")
            while len(buf) > max_line_buf:  # pathological: no newline for ages
                piece, buf = buf[:max_line_buf], buf[max_line_buf:]
                yield piece.decode("utf-8", errors="replace")
        if buf:
            yield buf.decode("utf-8", errors="replace").rstrip("\r")


def scan_secrets(files: list[Path], root: Path) -> list[str]:
    """Return 'file:line looks like a <label>' strings. Never the value."""
    problems: list[str] = []
    for f in files:
        try:
            rel = f.relative_to(root).as_posix()
        except ValueError:
            rel = str(f)
        try:
            size = f.stat().st_size
        except OSError as e:
            print(f"WARN cannot stat {rel}: {e}; file not secret-scanned")
            continue
        if size > LARGE_FILE_WARN_BYTES:
            print(f"WARN scanning large file {rel} ({size} bytes)")
        try:
            for i, line in enumerate(_iter_text_lines(f), 1):
                marked = CANARY_MARKER in line
                for rx, label in SECRET_PATTERNS:
                    hit = None
                    for m in rx.finditer(line):
                        # on a marked line only the known canary samples
                        # themselves are exempt; anything else still hits
                        if marked and m.group(0) in CANARY_SAMPLES:
                            continue
                        hit = m
                        break
                    if hit:
                        problems.append(f"{rel}:{i} looks like a {label}")
                        break
        except OSError as e:
            print(f"WARN cannot read {rel}: {e}; file not secret-scanned")
            continue
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
        file_names = {n for n in names if not n.endswith("/")}
        for n in names:
            if any(p in DENY_NAMES for p in n.replace("\\", "/").split("/")):
                raise BundleError(f"Bundle contains forbidden local-state file: {n}")
        if "manifest.json" not in names:
            raise BundleError("Bundle is missing manifest.json")
        if "SHA256SUMS" not in names:
            raise BundleError("Bundle is missing SHA256SUMS")
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        # Bidirectional identity: the zip must contain exactly the entries
        # SHA256SUMS lists (plus SHA256SUMS itself). An extra unlisted file
        # would otherwise skip the checksum stage entirely and be unpacked
        # by _extract_bundle; a missing entry means the sums do not cover
        # the bundle they claim to.
        listed: set[str] = set()
        for line in zf.read("SHA256SUMS").decode("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            digest, sep, name = line.partition("  ")
            name = name.strip()
            if not sep or len(digest) != 64 or not name:
                errors.append(f"malformed SHA256SUMS line: {line[:72]}")
                continue
            listed.add(name)
            if name not in file_names:
                errors.append(f"SHA256SUMS lists missing entry: {name}")
                continue
            actual = hashlib.sha256(zf.read(name)).hexdigest()
            if actual != digest:
                errors.append(f"checksum mismatch: {name}")
        unlisted = sorted(file_names - listed - {"SHA256SUMS"})
        if unlisted:
            errors.append("SHA256SUMS does not cover bundle file(s): "
                          + ", ".join(unlisted))
    if errors:
        raise BundleError(
            "Bundle verification failed (corrupted or tampered):\n  "
            + "\n  ".join(errors)
        )
    return manifest


# ------------------------------------------------------------------- import

def _extract_bundle(root: Path, bundle_path: Path) -> list[Path]:
    """Extract the bundle into root. Returns the file paths it wrote, so a
    failed import can remove files that did not exist before."""
    written: list[Path] = []
    with zipfile.ZipFile(bundle_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            parts = safe_zip_parts(info.filename)
            if parts is None:
                raise BundleError(f"Unsafe path in bundle: {info.filename}")
            if parts[0] == "workspace" and len(parts) > 1 and _denied_prefix(parts[1:]):
                raise BundleError(
                    "Bundle contains path excluded from export scope: "
                    + info.filename)
            if any(p in DENY_NAMES for p in parts):
                raise BundleError(f"Bundle contains forbidden file: {info.filename}")
            top = parts[0]
            rest = parts[1:]
            if top == "workspace" and rest:
                # defense in depth: refuse writes into excluded directories
                # (.git/...) even if the sums list was re-signed by an
                # attacker -- export can never produce them legitimately
                if _denied(rest):
                    raise BundleError(
                        "Bundle writes into an excluded directory: "
                        + info.filename)
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
            written.append(dest)
    return written


def _remove_created(root: Path, created: list[Path], keep: set[str]) -> None:
    """Delete files an import wrote that the pre-import backup does not
    contain (i.e. files the import created)."""
    for p in created:
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            continue
        if rel in keep:
            continue
        if p.is_symlink():
            print(f"WARN import wrote through existing symlink {rel}; "
                  "not removing it during rollback")
            continue
        try:
            p.unlink()
        except OSError as e:
            print(f"WARN could not remove file created by import: {rel} ({e})")


def _restore_zip(root: Path, backup_zip: Path,
                 created: list[Path] | None = None) -> None:
    keep: set[str] = set()
    with zipfile.ZipFile(backup_zip) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            parts = safe_zip_parts(info.filename)
            if parts is None:
                raise BundleError(f"Unsafe path in backup: {info.filename}")
            keep.add("/".join(parts))
            dest = root.joinpath(*parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(info))
    if created:
        # restoring the backup alone would leave files the import had
        # created; remove them so "rolled back" is actually true
        _remove_created(root, created, keep)


def _undo_created_links(actions: list) -> None:
    """Best-effort removal of links the re-link step created, so a rollback
    does not leave them pointing at restored/removed state. Foreign content
    replaced during re-link stays under backups/."""
    for a in actions:
        if a.action in ("none", "skip"):
            continue
        try:
            remove_managed(a.target)
        except (LinkError, OSError):
            continue


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

    created: list[Path] = []
    actions: list = []
    try:
        created = _extract_bundle(root, bundle_path)
        if environment:
            env_mod.set_environment(root, environment)
        mdir = root / "manifests"
        mdir.mkdir(parents=True, exist_ok=True)
        (mdir / f"{bundle_path.stem}.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        # re-link + doctor: a failure here is an import failure too, so it
        # stays inside the same rollback protection ("Rolled back" must be
        # true; doctor's non-zero exit is reported, not rolled back)
        try:
            env_now, _ = env_mod.resolve(root)
        except env_mod.EnvError:
            env_now = None
        cfg = build_effective(root, env_now)
        lm = LinkManager.from_config(root, cfg)
        actions = lm.plan(cfg.enabled_skills)
        for line in lm.apply(actions):
            print(line)

        print()
        print("Running doctor ...")
        rc = print_checks(run_checks(root))
    except Exception as e:
        print(f"FAIL import failed: {e}")
        print("Rolling back ...")
        if actions:
            _undo_created_links(actions)
            if any(a.action == "backup-replace" for a in actions):
                print("  foreign directories replaced during re-link are "
                      "kept under backups/")
        if backup:
            _restore_zip(root, backup, created)
            print(f"Rolled back to previous state ({backup.name})")
        elif created:
            _remove_created(root, created, keep=set())
            print("Removed files written by the failed import")
        raise BundleError(f"import failed: {e}") from e

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
