"""CLI environment contract: doctor honors --env; a bad --env fails loudly.

Review items: doctor ignored the global --env entirely, and status swallowed
an invalid --env into a misleading "(not set)" line with exit 0. Both now go
through the same resolution entry point as link/update: an explicitly
requested but unknown environment is ERROR + exit 2.
"""
from __future__ import annotations

import pytest

from agentctl.cli import main
from agentctl.doctor import run_checks


@pytest.fixture(autouse=True)
def isolated_host_env(monkeypatch):
    """conftest.py deliberately has no env isolation yet (workspace review
    R1); every CLI-level test here must shed the host's persistent markers so
    --root/tmp workspaces are used instead of the real one."""
    monkeypatch.delenv("AGENT_WORKSPACE_ROOT", raising=False)
    monkeypatch.delenv("AGENTCTL_ENV", raising=False)


def write_local_env(ws, env: str) -> None:
    (ws / "local.yaml").write_text(f"environment: {env}\n", encoding="utf-8")


@pytest.fixture
def ws_with_secrets(ws):
    """conftest's common.yaml requires TOKEN_A; satisfy it so doctor exit
    codes in this module reflect the environment check, not missing secrets."""
    (ws / ".env").write_text("TOKEN_A=value-a\nTOKEN_B=value-b\n", encoding="utf-8")
    return ws


# ------------------------------------------------------------------ doctor

def test_doctor_honors_global_env(ws_with_secrets, capsys):
    code = main(["--root", str(ws_with_secrets), "--env", "personal", "doctor"])
    out = capsys.readouterr().out
    assert code == 0
    assert "[PASS] environment" in out
    assert "personal (from --env)" in out


def test_doctor_env_flag_beats_local_and_env_var(ws_with_secrets, capsys, monkeypatch):
    monkeypatch.setenv("AGENTCTL_ENV", "company")
    write_local_env(ws_with_secrets, "personal")
    code = main(["--root", str(ws_with_secrets), "--env", "personal", "doctor"])
    assert "personal (from --env)" in capsys.readouterr().out
    assert code == 0


def test_doctor_without_flag_still_resolves_local(ws_with_secrets, capsys):
    write_local_env(ws_with_secrets, "personal")
    code = main(["--root", str(ws_with_secrets), "doctor"])
    assert "personal (from local.yaml)" in capsys.readouterr().out
    assert code == 0


def test_doctor_invalid_env_flag_errors(ws, capsys):
    code = main(["--root", str(ws), "--env", "bogus", "doctor"])
    captured = capsys.readouterr()
    assert code == 2
    assert "ERROR" in captured.err
    assert "Unknown environment 'bogus'" in captured.err


def test_doctor_without_any_env_still_runs_and_reports_gap(ws_with_secrets, capsys):
    # no --env, no AGENTCTL_ENV, no local.yaml: doctor is the troubleshooting
    # entry point, so it must run and show the missing environment as FAIL.
    code = main(["--root", str(ws_with_secrets), "doctor"])
    out = capsys.readouterr().out
    assert code == 1  # environment FAIL -> doctor exits 1
    assert "[FAIL] environment" in out
    assert "bootstrap" in out


def test_run_checks_env_parameter_used_directly(ws):
    checks = {c.name: c.detail for c in run_checks(ws, env="company", env_source="--env")}
    assert checks["environment"] == "company (from --env)"


# ------------------------------------------------------------------ status

def test_status_invalid_env_flag_errors_with_exit_2(ws, capsys):
    code = main(["--root", str(ws), "--env", "bogus", "status"])
    captured = capsys.readouterr()
    assert code == 2
    assert "ERROR" in captured.err
    assert "Unknown environment 'bogus'" in captured.err
    assert "(not set)" not in captured.out


def test_status_valid_env_flag_used(ws, capsys):
    code = main(["--root", str(ws), "--env", "personal", "status"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Environment   personal (from --env)" in out


def test_status_without_any_env_keeps_helpful_hint(ws, capsys):
    # preserved behavior: fresh machine, nothing configured -> the status
    # screen still renders with the bootstrap hint (and exit 0)
    code = main(["--root", str(ws), "status"])
    out = capsys.readouterr().out
    assert code == 0
    assert "(not set - run: agentctl bootstrap" in out


def test_status_uses_local_yaml_marker(ws, capsys):
    write_local_env(ws, "company")
    code = main(["--root", str(ws), "status"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Environment   company (from local.yaml)" in out


# ------------------------------------------------- dependency health check

def test_doctor_checks_both_runtime_dependencies(ws):
    checks = {c.name: c.status for c in run_checks(ws, env="personal", env_source="--env")}
    assert "pyyaml" in checks
    assert "ruamel.yaml" in checks  # discovery/storage.py imports it
    assert checks["pyyaml"] == "PASS"
    assert checks["ruamel.yaml"] == "PASS"
