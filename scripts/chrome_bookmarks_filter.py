#!/usr/bin/env python3
"""Generate an intranet-only variant of a captured Chrome Bookmarks file.

Reads a full Chrome ``Bookmarks`` JSON (as captured by
``agentctl appconfig capture chrome-bookmarks``) and writes a variant that
keeps exactly ONE folder (default: ``Innostar``) from the bookmark bar:

  - the matched folder and its whole subtree are preserved verbatim
    (ids, guids, dates, nesting);
  - every other bookmark-bar entry is dropped; the ``other`` and ``synced``
    roots are emptied;
  - the stale ``checksum`` and ``sync_metadata`` fields are removed
    (the edited content can no longer match them; Chrome reloads a
    checksum-less file fine and recomputes on next write).

The intranet machine then deploys this variant with the same appconfig
declaration, so only the work-related folder exists there:

    agentctl appconfig deploy chrome-bookmarks --from chrome-bookmarks-innostar.zip

Output layout mirrors an appconfig capture dir (``Bookmarks`` +
``manifest.json`` + ``SHA256SUMS.txt``), and ``--zip`` packs it the same
way ``agentctl appconfig capture --zip`` does, so the private-channel
audit convention (manifest + SHA-256) holds for the variant too.

This script is self-contained on purpose (no agentctl import): it must
run anywhere a capture dir exists, with only the Python stdlib.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


class BookmarksFilterError(RuntimeError):
    pass


# ------------------------------------------------------------- bookmarks io

def load_bookmarks(path: Path) -> dict:
    """Parse a Chrome Bookmarks JSON and validate the minimal shape."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise BookmarksFilterError(f"not valid JSON: {path}: {e}") from e
    except OSError as e:
        raise BookmarksFilterError(f"cannot read {path}: {e}") from e
    roots = data.get("roots")
    if not isinstance(roots, dict) or "bookmark_bar" not in roots:
        raise BookmarksFilterError(f"no roots.bookmark_bar in {path} - "
                                   f"is this really a Chrome Bookmarks file?")
    return data


def find_folders(data: dict, name: str) -> list[tuple[str, dict]]:
    """Exact-name folder matches across the top-level roots, in order
    bookmark_bar -> other -> synced. Returns (root_name, node) pairs."""
    hits: list[tuple[str, dict]] = []
    for root_name in ("bookmark_bar", "other", "synced"):
        root = data["roots"].get(root_name) or {}
        for child in root.get("children") or []:
            if child.get("type") == "folder" and child.get("name") == name:
                hits.append((root_name, child))
    return hits


def count_bookmarks(node: dict) -> int:
    """Number of URL bookmarks inside a subtree (folders excluded)."""
    total = 0
    for child in node.get("children") or []:
        if child.get("type") == "url":
            total += 1
        elif child.get("type") == "folder":
            total += count_bookmarks(child)
    return total


def build_variant(data: dict, folder_name: str) -> dict:
    """Return a new Bookmarks dict keeping only the named folder."""
    hits = find_folders(data, folder_name)
    if not hits:
        raise BookmarksFilterError(
            f"no folder named {folder_name!r} in bookmark_bar/other/synced "
            f"of the source file")
    if len(hits) > 1:
        where = ", ".join(root for root, _ in hits)
        raise BookmarksFilterError(
            f"folder {folder_name!r} is ambiguous (found in: {where}); "
            f"rename one of them or filter manually")

    root_name, folder = hits[0]
    roots_out: dict = {}
    for name, root in data["roots"].items():
        if not isinstance(root, dict):
            roots_out[name] = copy.deepcopy(root)
            continue
        if name == root_name:
            root = dict(root)
            root["children"] = [copy.deepcopy(folder)]
        else:
            root = dict(root)
            root["children"] = []
        roots_out[name] = root

    out = {k: copy.deepcopy(v) for k, v in data.items()
           if k not in ("roots", "checksum", "sync_metadata")}
    out["roots"] = roots_out
    return out


# ------------------------------------------------------------------ output

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_variant(variant: dict, out_dir: Path, src: Path,
                  folder_name: str, dry_run: bool = False) -> Path:
    """Write Bookmarks + manifest.json + SHA256SUMS.txt into out_dir."""
    out_file = out_dir / "Bookmarks"
    payload = json.dumps(variant, ensure_ascii=False, indent=3) + "\n"
    urls = count_bookmarks(variant["roots"]["bookmark_bar"]["children"][0])
    if dry_run:
        print(f"[dry-run] would write {out_file} "
              f"(1 folder '{folder_name}', {urls} bookmark(s))")
        return out_file

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file.write_text(payload, encoding="utf-8")

    manifest = {
        "app": "chrome-bookmarks",
        "variant": f"intranet-only: folder '{folder_name}'",
        "source": str(src),
        "source_sha256": _sha256(src),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "file_count": 1,
        "total_bytes": out_file.stat().st_size,
        "bookmark_urls": urls,
        "files": [{"path": "Bookmarks", "size": out_file.stat().st_size}],
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "SHA256SUMS.txt").write_text(
        f"{_sha256(out_file)}  Bookmarks\n", encoding="utf-8")

    print(f"Variant written: {out_file}")
    print(f"  kept folder '{folder_name}' with {urls} bookmark(s); "
          f"other roots emptied; checksum/sync_metadata removed")
    print(f"  manifest.json + SHA256SUMS.txt written")
    return out_file


def zip_variant(out_dir: Path, dry_run: bool = False) -> Path:
    """Zip the variant dir beside itself (same layout as appconfig capture)."""
    zip_path = out_dir.with_suffix(".zip")
    sums_path = out_dir.parent / f"SHA256SUMS-{out_dir.name}.txt"
    if dry_run:
        print(f"[dry-run] would write {zip_path} + {sums_path.name}")
        return zip_path
    if not out_dir.is_dir():
        raise BookmarksFilterError(f"variant directory not found: {out_dir}")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # manifest/sums are part of the audited payload, same as an
        # appconfig capture ZIP.
        for p in sorted(out_dir.rglob("*")):
            if p.is_file() and not p.is_symlink():
                zf.write(p, p.relative_to(out_dir.parent).as_posix())
    sums_path.write_text(f"{_sha256(zip_path)}  {zip_path.name}\n", encoding="utf-8")
    print(f"ZIP   {zip_path}  ({zip_path.stat().st_size} bytes)")
    print(f"SHA-256 {_sha256(zip_path)}")
    print(f"SUMS  {sums_path.name}")
    return zip_path


# ---------------------------------------------------------------------- cli

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="从抓取的 Chrome Bookmarks 生成仅含指定文件夹的内网变体",
        epilog="示例: python scripts/chrome_bookmarks_filter.py "
               "--src user-data/chrome-bookmarks/Bookmarks "
               "--folder Innostar --out user-data/chrome-bookmarks-innostar --zip")
    parser.add_argument("--src", required=True,
                        help="完整 Bookmarks JSON 路径（appconfig capture 产物）")
    parser.add_argument("--folder", default="Innostar",
                        help="要保留的书签文件夹名（默认 Innostar，精确匹配）")
    parser.add_argument("--out", required=True,
                        help="输出目录（内含 Bookmarks + manifest + SHA256SUMS）")
    parser.add_argument("--zip", action="store_true",
                        help="输出目录旁打成 <目录名>.zip（内网机部署用）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只显示将要写入的内容，不落盘")
    args = parser.parse_args(argv)

    try:
        src = Path(args.src).expanduser()
        out_dir = Path(args.out).expanduser()
        data = load_bookmarks(src)
        variant = build_variant(data, args.folder)
        write_variant(variant, out_dir, src, args.folder, dry_run=args.dry_run)
        if args.zip:
            zip_variant(out_dir, dry_run=args.dry_run)
    except BookmarksFilterError as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
