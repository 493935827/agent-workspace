"""Manifest generation and checksum coverage."""
import zipfile
from datetime import datetime

from agentctl.bundle import export_bundle, read_manifest_and_verify


def test_manifest_fields_and_sums_coverage(ws, tmp_path):
    out = export_bundle(ws, output=tmp_path / "b.zip")
    manifest = read_manifest_and_verify(out)  # also verifies every checksum

    assert manifest["version"] == "0.1.0"
    assert manifest["git_commit"] is None  # fixture workspace is not a git repo
    assert set(manifest["skills"]) >= {"alpha", "beta", "gamma"}
    assert manifest["agents"] == ["example"]
    assert manifest["python_packages"] == ["pyyaml>=6.0", "ruamel.yaml>=0.18,<0.19"]
    assert manifest["export_mode"] == "walk"
    datetime.fromisoformat(manifest["created_at"])  # parses as ISO-8601

    with zipfile.ZipFile(out) as zf:
        sums = [l for l in zf.read("SHA256SUMS").decode("utf-8").splitlines() if l.strip()]
        file_entries = [n for n in zf.namelist() if not n.endswith("/")]

    # SHA256SUMS is written last and does not hash itself
    assert len(sums) == len(file_entries) - 1
    assert manifest["file_count"] == len(
        [n for n in file_entries if n.startswith("workspace/")])

    # every line is "<64 hex chars>  <path>"
    for line in sums:
        digest, sep, name = line.partition("  ")
        assert sep == "  " and len(digest) == 64 and name


def test_sums_identity_covers_every_bundle_file(ws, tmp_path):
    # 双向恒等：zip 内文件集合 == SHA256SUMS 条目集合 ∪ {SHA256SUMS}；
    # 未列出与缺失条目都在 import 校验时被拒（防夹带注入）
    out = export_bundle(ws, output=tmp_path / "b.zip")
    with zipfile.ZipFile(out) as zf:
        file_entries = {n for n in zf.namelist() if not n.endswith("/")}
        listed = set()
        for line in zf.read("SHA256SUMS").decode("utf-8").splitlines():
            if line.strip():
                listed.add(line.partition("  ")[2])
    assert file_entries == listed | {"SHA256SUMS"}
