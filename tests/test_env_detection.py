"""Environment detection precedence: --env flag > AGENTCTL_ENV > local.yaml."""
import pytest

from agentctl import environment as env_mod


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