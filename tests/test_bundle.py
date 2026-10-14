"""Offline bundle: exclusion rules, verification, roundtrip import, safety."""
import zipfile

import pytest

from agentctl.bundle import (BundleError, export_bundle, import_bundle,
                             read_manifest_and_verify)


def test_export_excludes_local_state_and_env(ws, tmp_path):
    (ws / ".env").write_text("TOKEN_A=supersecret\n", encoding="utf-8")
    (ws / "local.yaml").write_text("environment: personal\n", encoding="utf-8")

    out = export_bundle(ws, output=tmp_path / "b.zip")

    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert not any(n.endswith("/.env") or n == ".env" for n in names)
    assert not any("local.yaml" in n for n in names)

    manifest = read_manifest_and_verify(out)
    assert manifest["version"] == "0.1.0"
    assert "alpha" in manifest["skills"]
    assert (ws / "manifests").is_dir()  # audit copy kept locally


def test_roundtrip_import_restores_files_and_keeps_local_state(ws, tmp_path):
    (ws / "skills" / "alpha" / "SKILL.md").write_text("alpha v2\n", encoding="utf-8")
    out = export_bundle(ws, output=tmp_path / "b.zip")

    # the "intranet machine" drifted to an older file
    (ws / "skills" / "alpha" / "SKILL.md").write_text("alpha v1\n", encoding="utf-8")
    # machine-local state that must survive an import untouched
    (ws / "local.yaml").write_text("environment: personal\n", encoding="utf-8")
    (ws / ".env").write_text("TOKEN_A=zzz\n", encoding="utf-8")

    rc = import_bundle(ws, out)

    assert rc == 0
    assert (ws / "skills" / "alpha" / "SKILL.md").read_text(encoding="utf-8") == "alpha v2\n"
    assert (ws / "local.yaml").read_text(encoding="utf-8") == "environment: personal\n"
    assert (ws / ".env").read_text(encoding="utf-8") == "TOKEN_A=zzz\n"
    assert list((ws / "backups").glob("workspace-v*.zip")), "import must back up first"


def test_tampered_bundle_rejected(ws, tmp_path):
    out = export_bundle(ws, output=tmp_path / "b.zip")

    src = tmp_path / "rezip"
    with zipfile.ZipFile(out) as zf:
        zf.extractall(src)
    (src / "workspace" / "skills" / "alpha" / "SKILL.md").write_text("tampered\n",
                                                                     encoding="utf-8")
    out2 = tmp_path / "b2.zip"
    with zipfile.ZipFile(out2, "w") as zf:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(src).as_posix())

    with pytest.raises(BundleError, match="checksum"):
        read_manifest_and_verify(out2)


def test_downgrade_requires_force(ws, tmp_path):
    (ws / "VERSION").write_text("2.0.0\n", encoding="utf-8")
    out = export_bundle(ws, output=tmp_path / "b.zip")  # bundle v2.0.0
    (ws / "VERSION").write_text("2.1.0\n", encoding="utf-8")  # workspace now newer

    rc = import_bundle(ws, out)
    assert rc == 1
    assert (ws / "VERSION").read_text(encoding="utf-8") == "2.1.0\n"


def test_secret_scan_blocks_export(ws, tmp_path):
    (ws / "skills" / "alpha" / "notes.md").write_text(
        "my key: sk-abcdefghijklmnopqrstuvwx\n", encoding="utf-8")  # agentctl-canary
    with pytest.raises(BundleError, match="notes.md"):
        export_bundle(ws, output=tmp_path / "b.zip")


def test_secret_scan_allows_marked_canary_lines(ws, tmp_path):
    (ws / "skills" / "alpha" / "canary.md").write_text(
        "sample: sk-abcdefghijklmnopqrstuvwx  # agentctl-canary\n", encoding="utf-8")
    out = export_bundle(ws, output=tmp_path / "b.zip")  # must not raise
    assert out.exists()


def test_secret_scan_ignores_hyphenated_url_slugs(ws, tmp_path):
    # regression: Microsoft Learn URLs in ui-ux-pro-max stack CSVs end in
    # 'task-based-asynchronous-programming', whose 'sk-based-...' substring
    # used to trip the OpenAI-key pattern and block export
    (ws / "skills" / "alpha" / "winui.csv").write_text(
        "28,Threading,Use Task.Run for CPU-bound work,High,"
        "https://learn.microsoft.com/en-us/dotnet/standard/parallel-programming/"
        "task-based-asynchronous-programming,active,2026-08-13\n",
        encoding="utf-8")
    out = export_bundle(ws, output=tmp_path / "b.zip")  # must not raise
    assert out.exists()


def test_secret_scan_blocks_prefixed_api_keys(ws, tmp_path):
    for i, key in enumerate((
        "sk-proj-q1w2e3r4t5y6u7i8o9p0z1x2",       # agentctl-canary
        "sk-ant-api03-q1w2e3r4t5y6u7i8o9p0z1x2",  # agentctl-canary
        "sk-or-v1-q1w2e3r4t5y6u7i8o9p0z1x2",      # agentctl-canary
    )):
        (ws / "skills" / "alpha" / f"key{i}.md").write_text(
            f"token: {key}\n", encoding="utf-8")
    with pytest.raises(BundleError, match=r"(?s)key0\.md.*key1\.md.*key2\.md"):
        export_bundle(ws, output=tmp_path / "b.zip")


def test_export_dry_run_writes_nothing(ws, tmp_path):
    out = tmp_path / "b.zip"
    export_bundle(ws, output=out, dry_run=True)
    assert not out.exists()
    assert not (ws / "dist").exists() or not any((ws / "dist").iterdir())