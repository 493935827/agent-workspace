"""appconfig: app config capture/deploy with backup-first and zip safety."""
import argparse
import json
import zipfile

import pytest

from agentctl.appconfig import (
    AppConfigError,
    _expand_path,
    capture,
    deploy,
    get_app,
    load_app_configs,
    match_files,
    run,
    status,
    zip_capture,
)
from agentctl.cli import build_parser
from agentctl.config import EffectiveConfig, merge


def cfg_with(spec: dict) -> EffectiveConfig:
    return EffectiveConfig(environment=None, raw={"app_configs": spec})


@pytest.fixture
def copyq_ws(tmp_path):
    """A fake %APPDATA%/copyq plus a one-app config."""
    target = tmp_path / "appdata" / "copyq"
    target.mkdir(parents=True)
    (target / "copyq.ini").write_text("[Options]\nmaxitems=200\n", encoding="utf-8")
    (target / "copyq-commands.ini").write_text("[Commands]\nsize=1\n", encoding="utf-8")
    (target / "copyq_tab_a.dat").write_bytes(b"\x00\x01history-a")
    (target / "copyq_tab_b.dat").write_bytes(b"\x02history-b")
    (target / "copyq-bak.ini").write_text("old", encoding="utf-8")
    (target / "copyq.log").write_text("log", encoding="utf-8")
    spec = {
        "copyq": {
            "description": "CopyQ",
            "target": str(target),
            "include": ["copyq.ini", "copyq-commands.ini",
                        "copyq_tabs.ini", "copyq_tab_*.dat"],
            "exclude": ["*.log"],
        }
    }
    return tmp_path, target, cfg_with(spec)


# ------------------------------------------------------------- declarations

def test_expand_path_env_and_tilde(monkeypatch, tmp_path):
    monkeypatch.setenv("FAKEAPPDATA", str(tmp_path / "app"))
    assert _expand_path("%FAKEAPPDATA%/copyq") == tmp_path / "app" / "copyq"
    assert _expand_path("~/x").is_absolute()


def test_load_requires_target(tmp_path):
    with pytest.raises(AppConfigError):
        load_app_configs(tmp_path, cfg_with({"x": {"include": ["a"]}}))


def test_get_app_unknown_lists_declared(copyq_ws):
    tmp, _, cfg = copyq_ws
    with pytest.raises(AppConfigError, match="copyq"):
        get_app(tmp, cfg, "nope")


def test_app_configs_dict_merges_across_layers():
    base = {"app_configs": {"copyq": {"include": ["copyq.ini"]}}}
    over = {"app_configs": {"copyq": {"description": "CopyQ"}}}
    merged = merge(base, over)
    assert merged["app_configs"]["copyq"]["include"] == ["copyq.ini"]
    assert merged["app_configs"]["copyq"]["description"] == "CopyQ"


# ------------------------------------------------------------------- match

def test_match_include_exclude(copyq_ws):
    tmp, target, cfg = copyq_ws
    app = load_app_configs(tmp, cfg)["copyq"]
    names = [p.name for p in match_files(target, app.include, app.exclude)]
    assert names == ["copyq-commands.ini", "copyq.ini",
                     "copyq_tab_a.dat", "copyq_tab_b.dat"]


def test_match_directory_pattern(tmp_path):
    target = tmp_path / "t"
    (target / "themes").mkdir(parents=True)
    (target / "themes" / "dark.ini").write_text("x", encoding="utf-8")
    (target / "loose.ini").write_text("x", encoding="utf-8")
    got = match_files(target, ["themes/"], [])
    assert [p.name for p in got] == ["dark.ini"]


# ----------------------------------------------------------------- capture

def test_capture_writes_manifest_and_sums(copyq_ws):
    tmp, _, cfg = copyq_ws
    app = get_app(tmp, cfg, "copyq")
    out = tmp / "user-data" / "copyq"
    files = capture(app, out)
    assert len(files) == 4
    assert (out / "copyq.ini").is_file()
    assert not (out / "copyq.log").exists()
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["file_count"] == 4
    assert manifest["total_bytes"] == sum(f.stat().st_size for f in files)
    assert any(e["path"] == "copyq_tab_a.dat" for e in manifest["files"])
    sums = (out / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert "copyq.ini" in sums and "copyq_tab_b.dat" in sums


def test_capture_dry_run_writes_nothing(copyq_ws):
    tmp, _, cfg = copyq_ws
    app = get_app(tmp, cfg, "copyq")
    out = tmp / "user-data" / "copyq"
    capture(app, out, dry_run=True)
    assert not out.exists()


def test_capture_no_match_raises(copyq_ws):
    tmp, _, cfg = copyq_ws
    cfg.raw["app_configs"]["copyq"]["include"] = ["missing_*.dat"]
    with pytest.raises(AppConfigError):
        capture(get_app(tmp, cfg, "copyq"), tmp / "out")


def test_zip_capture_roundtrip(copyq_ws):
    tmp, _, cfg = copyq_ws
    app = get_app(tmp, cfg, "copyq")
    out = tmp / "user-data" / "copyq"
    capture(app, out)
    zip_path = zip_capture(out)
    assert zip_path == tmp / "user-data" / "copyq.zip"
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert "copyq/copyq.ini" in names
        assert "copyq/manifest.json" in names
    sums = (tmp / "user-data" / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert sums.startswith(sha256_of(zip_path))


def test_zip_capture_requires_dir(tmp_path):
    with pytest.raises(AppConfigError):
        zip_capture(tmp_path / "missing")


def sha256_of(path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------ deploy

def test_deploy_from_dir_backup_first(copyq_ws):
    tmp, target, cfg = copyq_ws
    src = tmp / "src"
    src.mkdir()
    (src / "copyq.ini").write_text("NEW", encoding="utf-8")
    (src / "copyq_tab_new.dat").write_bytes(b"n")
    app = get_app(tmp, cfg, "copyq")

    assert deploy(app, src, tmp) == 0
    assert (target / "copyq.ini").read_text(encoding="utf-8") == "NEW"
    assert (target / "copyq_tab_new.dat").exists()
    old = list((tmp / "backups" / "appconfig" / "copyq").rglob("copyq.ini"))
    assert len(old) == 1
    assert old[0].read_text(encoding="utf-8") == "[Options]\nmaxitems=200\n"
    # untouched unrelated files stay
    assert (target / "copyq-bak.ini").read_text(encoding="utf-8") == "old"


def test_deploy_dry_run_changes_nothing(copyq_ws):
    tmp, target, cfg = copyq_ws
    src = tmp / "src"
    src.mkdir()
    (src / "copyq.ini").write_text("NEW", encoding="utf-8")
    before = (target / "copyq.ini").read_text(encoding="utf-8")
    assert deploy(get_app(tmp, cfg, "copyq"), src, tmp, dry_run=True) == 0
    assert (target / "copyq.ini").read_text(encoding="utf-8") == before
    assert not list((tmp / "backups").rglob("*"))


def test_deploy_from_zip_with_top_dir(copyq_ws):
    tmp, target, cfg = copyq_ws
    zip_path = tmp / "copyq-config.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("copyq/copyq.ini", "FROMZIP")
        zf.writestr("copyq/copyq_tab_z.dat", "z")
    assert deploy(get_app(tmp, cfg, "copyq"), zip_path, tmp) == 0
    assert (target / "copyq.ini").read_text(encoding="utf-8") == "FROMZIP"
    assert (target / "copyq_tab_z.dat").read_bytes() == b"z"


def test_deploy_zip_without_top_dir(copyq_ws):
    tmp, target, cfg = copyq_ws
    zip_path = tmp / "flat.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("copyq.ini", "FLAT")
    assert deploy(get_app(tmp, cfg, "copyq"), zip_path, tmp) == 0
    assert (target / "copyq.ini").read_text(encoding="utf-8") == "FLAT"


def test_deploy_rejects_unsafe_zip(copyq_ws):
    tmp, _, cfg = copyq_ws
    zip_path = tmp / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../evil.txt", "x")
    with pytest.raises(AppConfigError, match="unsafe"):
        deploy(get_app(tmp, cfg, "copyq"), zip_path, tmp)


def test_deploy_no_match_and_missing_source(copyq_ws):
    tmp, _, cfg = copyq_ws
    src = tmp / "empty"
    src.mkdir()
    with pytest.raises(AppConfigError):
        deploy(get_app(tmp, cfg, "copyq"), src, tmp)
    with pytest.raises(AppConfigError):
        deploy(get_app(tmp, cfg, "copyq"), tmp / "nope.zip", tmp)


# ------------------------------------------------------------- status / run

def test_status_ok_and_fail(copyq_ws, capsys):
    tmp, _, cfg = copyq_ws
    assert status(get_app(tmp, cfg, "copyq")) == 0
    cfg.raw["app_configs"]["copyq"]["target"] = str(tmp / "gone")
    assert status(get_app(tmp, cfg, "copyq")) == 1


def test_run_dispatch_status_and_capture(copyq_ws):
    tmp, _, cfg = copyq_ws
    args = argparse.Namespace(appconfig_command="status", name="copyq")
    assert run(tmp, cfg, args) == 0
    args = argparse.Namespace(appconfig_command="capture", name="copyq",
                              out=None, zip=False, dry_run=True)
    assert run(tmp, cfg, args) == 0
    assert not (tmp / "user-data" / "copyq").exists()


def test_cli_parses_appconfig():
    args = build_parser().parse_args(
        ["appconfig", "deploy", "copyq", "--from", "x.zip", "--dry-run"])
    assert args.appconfig_command == "deploy"
    assert args.from_src == "x.zip"
    assert args.dry_run
    args = build_parser().parse_args(["appconfig", "capture", "copyq", "--zip"])
    assert args.appconfig_command == "capture" and args.zip
