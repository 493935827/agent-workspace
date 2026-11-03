"""Environment detection precedence: --env flag > AGENTCTL_ENV > local.yaml.

Also covers workspace root detection precedence: explicit --root >
AGENT_WORKSPACE_ROOT > cwd upward search.
"""
from pathlib import Path

import pytest

from agentctl import environment as env_mod
from agentctl.workspace import WorkspaceError, find_root


def _bare_workspace(base: Path) -> Path:
    """Minimal VERSION + configs/ tree; enough for find_root."""
    (base / "configs").mkdir(parents=True)
    (base / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    return base


def test_cli_flag_wins(ws, monkeypatch):
    monkeypatch.setenv("AGENTCTL_ENV", "company")
    (ws / "local.yaml").write_text("environment: personal\n", encoding="utf-8")
    assert env_mod.resolve(ws, "company") == ("company", "--env")


def test_env_var_beats_local_file(ws, monkeypatch):
    monkeypatch.setenv("AGENTCTL_ENV", "company")
    (ws / "local.yaml").write_text("environment: personal\n", encoding="utf-8")
    assert env_mod.resolve(ws) == ("company", "AGENTCTL_ENV")


def test_local_file_used(ws, monkeypatch):
    monkeypatch.delenv("AGENTCTL_ENV", raising=False)
    (ws / "local.yaml").write_text("environment: personal\n", encoding="utf-8")
    assert env_mod.resolve(ws) == ("personal", "local.yaml")


def test_unset_raises_with_guidance(ws, monkeypatch):
    monkeypatch.delenv("AGENTCTL_ENV", raising=False)
    with pytest.raises(env_mod.EnvError, match="bootstrap"):
        env_mod.resolve(ws)


def test_unknown_environment_rejected(ws):
    with pytest.raises(env_mod.EnvError, match="Available profiles"):
        env_mod.set_environment(ws, "bogus")


def test_set_environment_writes_and_is_idempotent(ws, monkeypatch):
    monkeypatch.delenv("AGENTCTL_ENV", raising=False)
    assert env_mod.set_environment(ws, "personal") is True
    assert (ws / "local.yaml").is_file()
    assert env_mod.set_environment(ws, "personal") is False
    assert env_mod.resolve(ws) == ("personal", "local.yaml")


# --- find_root precedence: explicit --root > AGENT_WORKSPACE_ROOT > cwd ---


def test_find_root_explicit_start_beats_env_var(tmp_path, monkeypatch):
    root_a = _bare_workspace(tmp_path / "a" / "ws")
    root_b = _bare_workspace(tmp_path / "b" / "ws")
    monkeypatch.setenv("AGENT_WORKSPACE_ROOT", str(root_b))
    assert find_root(root_a) == root_a.resolve()


def test_find_root_explicit_start_does_not_fall_back_to_env(tmp_path, monkeypatch):
    root_b = _bare_workspace(tmp_path / "b" / "ws")
    monkeypatch.setenv("AGENT_WORKSPACE_ROOT", str(root_b))
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(WorkspaceError, match="--root"):
        find_root(empty)


def test_find_root_env_var_used_without_explicit_start(tmp_path, monkeypatch):
    root_b = _bare_workspace(tmp_path / "b" / "ws")
    monkeypatch.setenv("AGENT_WORKSPACE_ROOT", str(root_b))
    assert find_root() == root_b.resolve()


def test_find_root_invalid_env_var_raises(tmp_path, monkeypatch):
    bogus = tmp_path / "not-a-workspace"
    bogus.mkdir()
    monkeypatch.setenv("AGENT_WORKSPACE_ROOT", str(bogus))
    with pytest.raises(WorkspaceError, match="AGENT_WORKSPACE_ROOT"):
        find_root()


def test_find_root_walks_up_from_subdirectory(ws):
    assert find_root(ws / "skills" / "alpha") == ws.resolve()


def test_find_root_searches_upward_from_cwd(ws, monkeypatch):
    monkeypatch.chdir(ws / "skills" / "alpha")
    assert find_root() == ws.resolve()