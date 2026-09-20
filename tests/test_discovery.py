"""Discovery contract tests: managers are mocked; writes stay in tmp workspaces."""
import json
import subprocess
from pathlib import Path

import pytest

from agentctl.cli import main
from agentctl.discovery import commands, providers, storage
from agentctl.discovery.compare import compare, exit_code
from agentctl.discovery.model import DiscoveryError, ProviderResult, Resource, declarations


SCOPE = "a" * 64
CANARY = "sk-" + "discoveryCanaryNeverPersist123456789"  # agentctl-canary


def ok(*resources, provider="npm", scope=SCOPE):
    return ProviderResult(provider, "success", scope, list(resources))


def package(name="example", ver="1.0.0", source="registry", provider="npm"):
    return Resource(provider, name, ver, source)


def mock_scan(monkeypatch, results):
    monkeypatch.setattr(providers, "scan", lambda names, cwd: [r for r in results if r.provider in names])


def invoke(ws, capsys, *args):
    code = main(["--root", str(ws), *args, "--json"])
    captured = capsys.readouterr()
    assert not captured.err
    return code, json.loads(captured.out)


@pytest.mark.parametrize("provider,text,expected", [
    ("uv", "ruff v0.9.1\n- ruff\n", [("ruff", "0.9.1", "registry")]),
    ("uv", "ruff v0.9.1 [required: >=0.8]\n- ruff\n", [("ruff", "0.9.1", "registry")]),
    ("uv", "ruff v0.9.1 [required: https://user:pass@example.com/x]\n- ruff\n", [("ruff", "0.9.1", "unknown")]),
    ("pipx", json.dumps({"venvs": {"ruff": {"metadata": {"main_package": {
        "package": "ruff", "package_version": "0.9.1", "package_or_url": "ruff==0.9.1"}}}}}),
     [("ruff", "0.9.1", "registry")]),
    ("vscode", "Microsoft.Python@2025.1.0\n", [("microsoft.python", "2025.1.0", "editor")]),
    ("winget", "Name       Id          Version Source\n-------------------------------------\n"
     "Example    Test.App    1.2.3   winget\n", [("Test.App", "1.2.3", "winget")]),
])
def test_parsers(provider, text, expected):
    parsed = getattr(providers, f"parse_{provider}")(text)
    assert [(r.id, r.version, r.source) for r in parsed] == expected


@pytest.mark.parametrize("provider", ["npm", "pnpm"])
def test_node_registry_and_unsafe_sources(provider):
    deps = {"dependencies": {
        "known": {"version": "1.2.0", "resolved": "https://registry.npmjs.org/known/-/known-1.2.0.tgz"},
        "secret-source": {"version": "2.0", "resolved": f"https://user:{CANARY}@registry.npmjs.org/x"},
        "local": {"version": "1.0", "link": True},
    }}
    parsed = providers.parse_node(provider, json.dumps([deps] if provider == "pnpm" else deps))
    assert [r.source for r in parsed] == ["registry", "unknown", "unknown"]
    assert CANARY not in json.dumps([r.to_dict() for r in parsed])


@pytest.mark.parametrize("provider,text", [
    ("uv", ""), ("pipx", '{"venvs":{}}'), ("vscode", ""),
    ("npm", "{}"), ("pnpm", "[]"),
    ("winget", "Name       Id          Version\n--------------------------------\n"),
])
def test_empty_provider_outputs(provider, text):
    parsed = providers.parse_node(provider, text) if provider in {"npm", "pnpm"} else getattr(providers, f"parse_{provider}")(text)
    assert parsed == []


@pytest.mark.parametrize("provider", list(providers.PROVIDERS))
def test_missing_and_invalid_provider_isolation(ws, monkeypatch, provider):
    monkeypatch.setattr(providers.shutil, "which", lambda name: None)
    assert providers.discover(provider, ws).status == "unavailable"
    monkeypatch.setattr(providers.shutil, "which", lambda name: "fake")
    monkeypatch.setattr(providers, "query", lambda *args: CANARY)
    result = providers.discover(provider, ws)
    if provider == "winget" and providers.os.name != "nt":
        assert result.status == "unavailable"
    else:
        assert result.status == "error"
    assert CANARY not in json.dumps(result.to_dict())


@pytest.mark.parametrize("failure,category", [("exit", "exit"), ("timeout", "timeout"), ("os", "execution"), ("encoding", "encoding")])
def test_query_failures_never_echo_raw(ws, monkeypatch, capsys, failure, category):
    def fake_run(*args, **kwargs):
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["env"]["UV_OFFLINE"] == "1"
        if failure == "timeout":
            raise subprocess.TimeoutExpired("tool", 45, output=CANARY, stderr=CANARY)
        if failure == "os":
            raise OSError(CANARY)
        return subprocess.CompletedProcess(args, 7 if failure == "exit" else 0,
                                           CANARY.encode() if failure == "exit" else b"\xff", CANARY.encode())
    monkeypatch.setattr(providers.subprocess, "run", fake_run)
    with pytest.raises(providers.QueryError) as exc:
        providers.query("fake", (), ws)
    assert exc.value.category == category
    assert CANARY not in str(exc.value)
    assert not capsys.readouterr().err


def test_compliance_and_history_are_independent():
    declared = {("npm", "same"): None, ("npm", "drift"): "2", ("npm", "missing"): None,
                ("npm", "unknown-version"): "1", ("pipx", "ruff"): None}
    results = [ok(package("same"), package("drift", "1"), package("new"),
                  package("unknown", source="unknown"), package("unknown-version", None)),
               ProviderResult("pipx", "unavailable")]
    rows = compare(declared, results, [ok()], {("npm", "same"), ("npm", "new")})
    by_id = {r["id"]: r for r in rows}
    assert {k: v["status"] for k, v in by_id.items()} == {
        "same": "MATCH", "drift": "DRIFT", "missing": "MISSING", "unknown-version": "INDETERMINATE",
        "ruff": "INDETERMINATE", "new": "NEW", "unknown": "UNKNOWN"}
    assert by_id["same"]["history"] == "RESTORED"
    assert not by_id["same"]["ignored"]
    assert by_id["new"]["ignored"]
    assert exit_code(results, rows) == 0
    assert exit_code(results, rows, True) == 2


def test_history_no_baseline_scope_version_disappearance():
    resource = package()
    assert compare({}, [ok(resource)])[0]["history"] == "NO_BASELINE"
    assert compare({}, [ok(resource)], [ok(scope="b" * 64)])[0]["history"] == "INCOMPARABLE"
    assert compare({}, [ok(resource)], [ok(package(ver="2"))])[0]["history"] == "VERSION_CHANGED"
    assert compare({}, [ok()], [ok(resource)])[0]["history"] == "DISAPPEARED"


def test_snapshot_commit_and_failure_preserves_baseline(ws, monkeypatch, capsys):
    mock_scan(monkeypatch, [ok(package())])
    code, data = invoke(ws, capsys, "snapshot", "--dry-run")
    assert code == 0 and not data["saved"] and not (ws / ".agentctl").exists()
    code, data = invoke(ws, capsys, "snapshot")
    assert code == 0 and data["saved"]
    original = storage.snapshot_path(ws).read_bytes()
    assert storage.load_snapshot(ws)[0].resources[0] == package()
    mock_scan(monkeypatch, [ProviderResult("npm", "error", error="parse")])
    code, data = invoke(ws, capsys, "snapshot")
    assert code == 2 and not data["saved"]
    assert storage.snapshot_path(ws).read_bytes() == original


def test_scan_adopt_diff_then_missing_acceptance(ws, monkeypatch, capsys):
    mock_scan(monkeypatch, [ok(package())])
    code, data = invoke(ws, capsys, "scan", "--provider", "npm", "--new")
    assert code == 0 and data["resources"][0]["status"] == "NEW"
    assert not (ws / ".agentctl").exists()
    code, data = invoke(ws, capsys, "adopt", "--provider", "npm", "--profile", "personal")
    assert len(data["candidates"]) == 1 and "adopted" not in data
    code, data = invoke(ws, capsys, "adopt", "npm:example", "--profile", "personal")
    assert code == 0 and len(data["adopted"]) == 1
    code, data = invoke(ws, capsys, "--env", "personal", "diff", "--provider", "npm", "--all", "--check")
    assert code == 0 and data["resources"][0]["status"] == "MATCH"
    mock_scan(monkeypatch, [ok()])
    code, data = invoke(ws, capsys, "--env", "personal", "diff", "--provider", "npm", "--check")
    assert code == 1 and data["resources"][0]["status"] == "MISSING"
    mock_scan(monkeypatch, [ProviderResult("npm", "unavailable")])
    code, data = invoke(ws, capsys, "--env", "personal", "diff", "--provider", "npm", "--check")
    assert code == 2 and data["resources"][0]["status"] == "INDETERMINATE"


def test_adopt_preserves_comments_locks_target_layers_and_local_notice(ws):
    common = ws / "configs/common.yaml"
    common.write_text('# retain me\nresources:\n  npm:\n    inherited: {version: "3.0"} # locked\n', encoding="utf-8")
    (ws / "local.yaml").write_text('resources:\n  npm:\n    fresh: {version: "9.0"}\n', encoding="utf-8")
    before = common.read_bytes()
    result = storage.adopt(ws, "personal", [package("inherited", "8.0"), package("fresh")], False, False)
    assert [r["id"] for r in result["adopted"]] == ["fresh"]
    assert result["local_overrides"][0]["effective_version"] == "9.0"
    assert common.read_bytes() == before
    storage.adopt(ws, "common", [package("fresh")], True, False)
    assert '# retain me' in common.read_text() and '# locked' in common.read_text()
    assert '"3.0"' in common.read_text()
    assert any(p.read_bytes() == before for p in (ws / ".agentctl/backups").glob("*.yaml"))


def test_adopt_dry_run_and_atomic_batch_pin_failure(ws):
    target = ws / "configs/personal.yaml"
    before = target.read_bytes()
    storage.adopt(ws, "personal", [package()], False, True)
    assert target.read_bytes() == before and not (ws / ".agentctl").exists()
    with pytest.raises(DiscoveryError):
        storage.adopt(ws, "personal", [package(), package("missing-version", None)], True, False)
    assert target.read_bytes() == before and not (ws / ".agentctl").exists()
    with pytest.raises(DiscoveryError):
        storage.adopt(ws, "personal", [package(source="unknown")], False, False)


def test_concurrent_edits_and_lock_are_not_overwritten(ws):
    target = ws / "configs/personal.yaml"
    old = target.read_bytes()
    target.write_text("# concurrent edit\n", encoding="utf-8")
    with pytest.raises(DiscoveryError, match="concurrent-modification"):
        storage.atomic_write(ws, target, b"new", old, backup=True)
    assert target.read_text() == "# concurrent edit\n"
    with storage.transaction(ws):
        with pytest.raises(DiscoveryError, match="write-locked"):
            storage.atomic_write(ws, target, b"new", target.read_bytes())


def test_ignore_only_hides_unregistered_and_can_remove(ws, monkeypatch, capsys):
    mock_scan(monkeypatch, [ok(package())])
    code, data = invoke(ws, capsys, "ignore", "npm:example")
    assert code == 0 and len(data["ignored"]) == 1
    code, data = invoke(ws, capsys, "scan", "--provider", "npm", "--new")
    assert not data["resources"]
    code, data = invoke(ws, capsys, "scan", "--provider", "npm", "--all")
    assert data["resources"][0]["ignored"]
    code, data = invoke(ws, capsys, "ignore", "--list")
    assert len(data["ignored"]) == 1
    code, data = invoke(ws, capsys, "ignore", "npm:example", "--remove")
    assert data["ignored"] == []


@pytest.mark.parametrize("where", ["config", "state", "ignore", "exception", "id", "source"])
def test_canary_never_reaches_output_or_new_persistence(ws, monkeypatch, capsys, where):
    mock_scan(monkeypatch, [ok(package())])
    if where == "config":
        (ws / "configs/common.yaml").write_text("bad: [" + CANARY, encoding="utf-8")
    elif where == "state":
        path = storage.snapshot_path(ws)
        path.parent.mkdir(parents=True)
        path.write_text(CANARY, encoding="utf-8")
    elif where == "ignore":
        path = storage.ignore_path(ws)
        path.parent.mkdir()
        path.write_text("ignored: [" + CANARY, encoding="utf-8")
    elif where == "exception":
        def fail(*args):
            raise OSError(CANARY)
        monkeypatch.setattr(providers, "scan", fail)
    elif where == "id":
        monkeypatch.setattr(providers.shutil, "which", lambda name: "fake")
        monkeypatch.setattr(providers, "query", lambda *args: json.dumps({"dependencies": {CANARY: {"version": "1"}}}))
        monkeypatch.setattr(providers, "scan", lambda names, root: [providers.discover("npm", root)])
    elif where == "source":
        resource = providers.parse_node("npm", json.dumps({"dependencies": {"example": {
            "version": "1", "resolved": f"https://user:{CANARY}@registry.npmjs.org/x"}}}))[0]
        mock_scan(monkeypatch, [ok(resource)])
    main(["--root", str(ws), "adopt", "npm:example", "--profile", "personal", "--json"])
    output = capsys.readouterr()
    assert CANARY not in output.out + output.err
    assert CANARY not in (ws / "configs/personal.yaml").read_text()
    assert not (ws / ".agentctl/backups").exists()


def test_explicit_null_unlock_and_old_config_compatibility(ws):
    from agentctl.config import merge, build_effective
    assert declarations(build_effective(ws, "personal").raw) == {}
    raw = merge({"resources": {"npm": {"a": {"version": "1"}}}},
                {"resources": {"npm": {"a": {"version": None}}}})
    assert declarations(raw) == {("npm", "a"): None}


def test_state_excluded_from_bundle_git_and_walk(ws, monkeypatch):
    from agentctl import bundle
    path = ws / ".agentctl/state/current.json"
    path.parent.mkdir(parents=True)
    path.write_text(CANARY, encoding="utf-8")
    monkeypatch.setattr(bundle.gitops, "is_repo", lambda root: False)
    files, _ = bundle.collect_files(ws)
    assert path not in files
    monkeypatch.setattr(bundle.gitops, "available", lambda: True)
    monkeypatch.setattr(bundle.gitops, "is_repo", lambda root: True)
    monkeypatch.setattr(bundle.gitops, "has_commits", lambda root: True)
    monkeypatch.setattr(bundle.gitops, "tracked_files", lambda root: [".agentctl/state/current.json", "VERSION"])
    files, _ = bundle.collect_files(ws)
    assert files == [ws / "VERSION"]


@pytest.mark.parametrize("provider,text", [
    ("uv", "some warning\n"), ("pipx", '{}'), ("vscode", "extension-without-version"),
    ("npm", '{"dependencies": []}'), ("pnpm", '{}'),
    ("winget", 'Name  Id  Version\n--------------------\nApp   Truncated…  1\n'),
])
def test_damaged_output_is_not_empty_success(provider, text):
    with pytest.raises((DiscoveryError, ValueError, TypeError, KeyError)):
        if provider in {"npm", "pnpm"}:
            providers.parse_node(provider, text)
        else:
            getattr(providers, f"parse_{provider}")(text)


def test_custom_profile_batch_pin_and_ignore_dry_run(ws, monkeypatch, capsys):
    path = ws / "configs/lab.yaml"
    path.write_text("# lab\n", encoding="utf-8")
    mock_scan(monkeypatch, [ok(package(), package("no-version", None))])
    code, data = invoke(ws, capsys, "adopt", "--all", "--provider", "npm", "--profile", "lab", "--pin-version")
    assert code == 2 and path.read_text() == "# lab\n"
    assert not (ws / ".agentctl").exists()
    code, data = invoke(ws, capsys, "ignore", "npm:example", "--dry-run")
    assert code == 0 and not (ws / ".agentctl").exists()
    code, data = invoke(ws, capsys, "adopt", "--all", "--provider", "npm", "--profile", "lab")
    assert code == 0 and len(data["adopted"]) == 2


def test_quick_does_not_check_unscanned_declarations_as_satisfied(ws, monkeypatch, capsys):
    (ws / "configs/common.yaml").write_text("resources:\n  winget:\n    Test.App: {version: null}\n", encoding="utf-8")
    mock_scan(monkeypatch, [ok()])
    code, data = invoke(ws, capsys, "diff", "--quick", "--check")
    assert code == 2 and data["resources"][0]["status"] == "INDETERMINATE"
    code, _ = invoke(ws, capsys, "diff", "--provider", "npm", "--check")
    assert code == 0


def test_replace_failure_keeps_original_and_cleans_transaction(ws, monkeypatch):
    path = ws / "configs/personal.yaml"
    original = path.read_bytes()
    def fail(*args):
        raise OSError("simulated-replace-failure")
    monkeypatch.setattr(storage.os, "replace", fail)
    with pytest.raises(OSError):
        storage.atomic_write(ws, path, b"new", original, backup=True)
    assert path.read_bytes() == original
    assert not (ws / ".agentctl/write.lock").exists()
    assert not list(path.parent.glob(".agentctl-*"))
    assert len(list((ws / ".agentctl/backups").glob("*.yaml"))) == 1


def test_backup_cannot_copy_recognizable_credentials(ws):
    path = ws / "configs/personal.yaml"
    path.write_text(f"accidental-secret: {CANARY}\n", encoding="utf-8")
    with pytest.raises(DiscoveryError, match="unsafe-shared-config"):
        storage.adopt(ws, "personal", [package()], False, False)
    assert not (ws / ".agentctl").exists()


def test_unavailable_snapshot_and_unknown_version_check(ws):
    result = ProviderResult("npm", "unavailable")
    storage.save_snapshot(ws, [result], None)
    assert storage.load_snapshot(ws)[0].status == "unavailable"
    assert compare({("npm", "a"): None}, [result], storage.load_snapshot(ws))[0]["history"] == "INCOMPARABLE"
    assert exit_code([result], [], True) == 0
    results = [ok(package(ver=None))]
    rows = compare({("npm", "example"): "1"}, results)
    assert exit_code(results, rows, True) == 2


def test_winget_approximate_versions_are_unknown():
    text = "Name       Id          Version   Source\n---------------------------------------\nApp        Test.App    > 1.0     winget\n"
    assert providers.parse_winget(text)[0].version is None


def test_multiple_installed_versions_preserve_presence_but_not_exact_version(ws, monkeypatch):
    monkeypatch.setattr(providers.shutil, "which", lambda name: "fake")
    monkeypatch.setattr(providers, "query", lambda *args: "pub.ext@1.0\npub.ext@2.0\n")
    result = providers.discover("vscode", ws)
    assert result.status == "success" and len(result.resources) == 1
    assert result.resources[0].version is None
