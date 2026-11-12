"""chrome_bookmarks_filter: intranet-only variant of a Chrome Bookmarks JSON."""
import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "chrome_bookmarks_filter.py"

spec = importlib.util.spec_from_file_location("chrome_bookmarks_filter", SCRIPT)
cbf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cbf)


def make_source(tmp_path: Path) -> tuple[Path, dict]:
    """A realistic Bookmarks JSON: Innostar folder on the bar, noise around."""
    innostar = {
        "type": "folder", "name": "Innostar", "id": "100", "guid": "g-innostar",
        "date_added": "13300000000000000",
        "children": [
            {"type": "url", "name": "portal", "id": "101", "guid": "g-portal",
             "url": "https://llm.innostar-semi.com/portal/"},
            {"type": "folder", "name": "Web", "id": "102", "guid": "g-web",
             "date_added": "13300000000000001",
             "children": [
                 {"type": "url", "name": "wiki", "id": "103", "guid": "g-wiki",
                  "url": "https://wiki.example/"}]},
        ],
    }
    data = {
        "checksum": "deadbeef",
        "sync_metadata": "base64-blob",
        "version": 1,
        "roots": {
            "bookmark_bar": {"type": "folder", "name": "书签栏", "id": "1",
                             "guid": "g-bar", "children": [
                                 {"type": "url", "name": "personal", "id": "5",
                                  "guid": "g-personal", "url": "https://game.example/"},
                                 innostar]},
            "other": {"type": "folder", "name": "其他书签", "id": "2",
                      "guid": "g-other", "children": [
                          {"type": "url", "name": "other-url", "id": "6",
                           "guid": "g-other-url", "url": "https://other.example/"}]},
            "synced": {"type": "folder", "name": "移动设备书签", "id": "3",
                       "guid": "g-synced", "children": []},
        },
    }
    src = tmp_path / "Bookmarks"
    src.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return src, data


# ------------------------------------------------------------------ lookup

def test_find_folders_exact_match_across_roots(tmp_path):
    src, data = make_source(tmp_path)
    hits = cbf.find_folders(data, "Innostar")
    assert [(root, node["id"]) for root, node in hits] == [("bookmark_bar", "100")]


def test_find_folders_no_match_is_empty(tmp_path):
    src, data = make_source(tmp_path)
    assert cbf.find_folders(data, "Innostar-ic") == []


# ----------------------------------------------------------------- variant

def test_variant_keeps_only_named_folder(tmp_path):
    src, data = make_source(tmp_path)
    out = cbf.build_variant(data, "Innostar")

    bar_children = out["roots"]["bookmark_bar"]["children"]
    assert [c["name"] for c in bar_children] == ["Innostar"]
    assert out["roots"]["other"]["children"] == []
    assert out["roots"]["synced"]["children"] == []
    # stale integrity/sync fields must not survive the edit
    assert "checksum" not in out
    assert "sync_metadata" not in out
    assert out["version"] == 1
    # subtree preserved verbatim (ids, guids, nesting)
    assert out["roots"]["bookmark_bar"]["children"][0]["guid"] == "g-innostar"
    assert out["roots"]["bookmark_bar"]["children"][0]["children"][1]["name"] == "Web"


def test_variant_does_not_mutate_source(tmp_path):
    src, data = make_source(tmp_path)
    cbf.build_variant(data, "Innostar")
    assert len(data["roots"]["bookmark_bar"]["children"]) == 2
    assert data["checksum"] == "deadbeef"
    assert data["sync_metadata"] == "base64-blob"


def test_variant_missing_folder_raises(tmp_path):
    src, data = make_source(tmp_path)
    with pytest.raises(cbf.BookmarksFilterError, match="no folder named"):
        cbf.build_variant(data, "不存在的文件夹")


def test_variant_ambiguous_folder_raises(tmp_path):
    dup = {"type": "folder", "name": "Innostar", "id": "9", "guid": "g-dup",
           "children": []}
    data = {"version": 1, "roots": {
        "bookmark_bar": {"children": [dup]},
        "other": {"children": [json.loads(json.dumps(dup))]},
        "synced": {"children": []}}}
    with pytest.raises(cbf.BookmarksFilterError, match="ambiguous"):
        cbf.build_variant(data, "Innostar")


def test_count_bookmarks_counts_urls_only():
    node = {"children": [
        {"type": "url"},
        {"type": "folder", "children": [{"type": "url"}, {"type": "folder",
                                                        "children": [{"type": "url"}]}]},
        {"type": "folder", "children": []},
    ]}
    assert cbf.count_bookmarks(node) == 3


# --------------------------------------------------------------- file stage

def test_write_variant_roundtrip_and_manifest(tmp_path):
    src, _ = make_source(tmp_path)
    out_dir = tmp_path / "chrome-bookmarks-innostar"
    data = cbf.load_bookmarks(src)
    variant = cbf.build_variant(data, "Innostar")
    out_file = cbf.write_variant(variant, out_dir, src, "Innostar")

    loaded = json.loads(out_file.read_text(encoding="utf-8"))
    assert loaded["roots"]["bookmark_bar"]["children"][0]["name"] == "Innostar"

    sums = (out_dir / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert sums == f"{cbf._sha256(out_file)}  Bookmarks\n"

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["app"] == "chrome-bookmarks"
    assert manifest["source_sha256"] == cbf._sha256(src)
    assert manifest["bookmark_urls"] == 2  # portal + wiki
    assert manifest["files"] == [{"path": "Bookmarks",
                                  "size": out_file.stat().st_size}]


def test_load_bookmarks_rejects_non_chrome_json(tmp_path):
    bad = tmp_path / "not-chrome.json"
    bad.write_text("{\"hello\": 1}", encoding="utf-8")
    with pytest.raises(cbf.BookmarksFilterError, match="bookmark_bar"):
        cbf.load_bookmarks(bad)


def test_load_bookmarks_rejects_invalid_json(tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(cbf.BookmarksFilterError, match="not valid JSON"):
        cbf.load_bookmarks(bad)


# --------------------------------------------------------------------- zip

def test_zip_variant_matches_appconfig_layout(tmp_path):
    src, _ = make_source(tmp_path)
    out_dir = tmp_path / "chrome-bookmarks-innostar"
    data = cbf.load_bookmarks(src)
    cbf.write_variant(cbf.build_variant(data, "Innostar"), out_dir, src, "Innostar")
    zip_path = cbf.zip_variant(out_dir)

    assert zip_path.read_bytes()[:2] == b"PK"
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    # entry order follows platform path sorting; membership is what matters
    assert names == {
        "chrome-bookmarks-innostar/Bookmarks",
        "chrome-bookmarks-innostar/SHA256SUMS.txt",
        "chrome-bookmarks-innostar/manifest.json",
    }
    sums = (tmp_path / "SHA256SUMS-chrome-bookmarks-innostar.txt")
    assert sums.read_text(encoding="utf-8").startswith(cbf._sha256(zip_path))


# --------------------------------------------------------------------- CLI

def run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, encoding="utf-8", timeout=60)


def test_cli_end_to_end(tmp_path):
    src, _ = make_source(tmp_path)
    out_dir = tmp_path / "variant"
    proc = run_cli(["--src", str(src), "--folder", "Innostar",
                    "--out", str(out_dir), "--zip"])
    assert proc.returncode == 0, proc.stderr
    assert (out_dir / "Bookmarks").exists()
    assert (out_dir.parent / "variant.zip").exists()


def test_cli_missing_folder_exit_code(tmp_path):
    src, _ = make_source(tmp_path)
    proc = run_cli(["--src", str(src), "--folder", "nope",
                    "--out", str(tmp_path / "variant")])
    assert proc.returncode == 1
    assert "no folder named" in proc.stderr


def test_cli_dry_run_writes_nothing(tmp_path):
    src, _ = make_source(tmp_path)
    out_dir = tmp_path / "variant"
    proc = run_cli(["--src", str(src), "--folder", "Innostar",
                    "--out", str(out_dir), "--zip", "--dry-run"])
    assert proc.returncode == 0, proc.stderr
    assert not out_dir.exists()
    assert not (out_dir.parent / "variant.zip").exists()
