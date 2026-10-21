"""machine_setup: idempotent user env vars, PATH, PowerShell policy/profile.

Every registry / profile helper is faked via monkeypatch; the real user
environment is never touched (same rule as the conftest sandbox).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agentctl import machine
from agentctl.config import EffectiveConfig, build_effective


def make_cfg(machine_setup: dict) -> EffectiveConfig:
    return EffectiveConfig(environment="personal", raw={"machine_setup": machine_setup})


class FakeUserReg:
    """In-memory HKCU\\Environment stand-in: name -> (value, reg_type)."""

    def __init__(self, values: dict | None = None):
        self.values: dict[str, tuple[str, int]] = dict(values or {})
        self.writes: list[tuple[str, str, int]] = []

    def read(self, name: str):
        return self.values.get(name)

    def write(self, name: str, value: str, vtype: int) -> None:
        self.values[name] = (value, vtype)
        self.writes.append((name, value, vtype))


@pytest.fixture
def fake_reg(monkeypatch) -> FakeUserReg:
    reg = FakeUserReg()
    monkeypatch.setattr(machine, "_read_user_value", reg.read)
    monkeypatch.setattr(machine, "_write_user_value", reg.write)
    monkeypatch.setattr(machine, "_broadcast_env_change", lambda: None)
    return reg


@pytest.fixture
def no_profiles(monkeypatch):
    """Keep the PowerShell profile step out of Windows-path tests."""
    monkeypatch.setattr(machine, "_powershell_profiles", lambda: [])


# ------------------------------------------------------------------ values

def test_resolve_value(tmp_path):
    root = tmp_path / "ws"
    assert machine._resolve_value("{root}", root) == str(root)
    assert machine._resolve_value("{root}/scripts", root) == str(root / "scripts")
    assert machine._resolve_value("plain-value", root) == "plain-value"


# ------------------------------------------------------- env vars and PATH

def test_env_and_path_set_then_idempotent(tmp_path, fake_reg, no_profiles):
    root = tmp_path / "ws"
    cfg = make_cfg({"env_vars": {"AGENT_WORKSPACE_ROOT": "{root}"},
                    "path_entries": ["{root}/scripts"]})

    machine._apply_windows(root, cfg.machine_setup, dry_run=False)
    assert fake_reg.values["AGENT_WORKSPACE_ROOT"] == (str(root), machine._REG_SZ)
    assert fake_reg.values["Path"][0] == str(root / "scripts")

    machine._apply_windows(root, cfg.machine_setup, dry_run=False)
    assert len(fake_reg.writes) == 2  # second run wrote nothing new
    assert fake_reg.values["Path"][0] == str(root / "scripts")  # no duplicate


def test_env_update_keeps_type_and_logs_old_value(tmp_path, fake_reg, no_profiles):
    root = tmp_path / "ws"
    fake_reg.values["AGENT_WORKSPACE_ROOT"] = ("D:\\old", machine._REG_EXPAND_SZ)
    cfg = make_cfg({"env_vars": {"AGENT_WORKSPACE_ROOT": "{root}"}})

    log = machine._apply_windows(root, cfg.machine_setup, dry_run=False)
    assert fake_reg.values["AGENT_WORKSPACE_ROOT"] == (str(root), machine._REG_EXPAND_SZ)
    assert any("was: D:\\old" in line for line in log)


def test_path_appends_preserving_order_and_expand_type(tmp_path, fake_reg, no_profiles):
    root = tmp_path / "ws"
    fake_reg.values["Path"] = ("C:\\one;%USERPROFILE%\\bin", machine._REG_EXPAND_SZ)
    cfg = make_cfg({"path_entries": ["{root}/scripts"]})

    machine._apply_windows(root, cfg.machine_setup, dry_run=False)
    value, vtype = fake_reg.values["Path"]
    assert value == f"C:\\one;%USERPROFILE%\\bin;{root / 'scripts'}"
    assert vtype == machine._REG_EXPAND_SZ  # kept because the value has %VAR%


def test_dry_run_writes_nothing(tmp_path, fake_reg, no_profiles):
    root = tmp_path / "ws"
    cfg = make_cfg({"env_vars": {"AGENT_WORKSPACE_ROOT": "{root}"},
                    "path_entries": ["{root}/scripts"]})

    log = machine._apply_windows(root, cfg.machine_setup, dry_run=True)
    assert fake_reg.writes == []
    assert fake_reg.values == {}
    assert any(line.startswith("[dry-run]") for line in log)


# --------------------------------------------------------- execution policy

def test_execution_policy_raise_only(tmp_path, monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(machine, "_reg_write",
                        lambda hive, path, name, value: calls.append((path, name, value)))

    monkeypatch.setattr(machine, "_effective_execution_policy",
                        lambda: ("Restricted", "default"))
    out = machine._ensure_execution_policy("RemoteSigned", dry_run=False)
    assert "Restricted -> RemoteSigned" in out
    assert calls[-1][2] == "RemoteSigned"

    monkeypatch.setattr(machine, "_effective_execution_policy",
                        lambda: ("Bypass", "CurrentUser"))
    out = machine._ensure_execution_policy("RemoteSigned", dry_run=False)
    assert "already Bypass" in out  # never lowered, never rewritten

    monkeypatch.setattr(machine, "_effective_execution_policy",
                        lambda: ("AllSigned", "MachinePolicy"))
    out = machine._ensure_execution_policy("RemoteSigned", dry_run=False)
    assert "MachinePolicy" in out  # GPO-managed: left untouched
    assert len(calls) == 1


# ------------------------------------------------------------ profile block

def test_profile_block_lifecycle(tmp_path):
    prof = tmp_path / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1"
    block = machine._block_content({"zoxide": "if (Get-Command zoxide) { }"})
    want = machine._block_bytes(block)

    # 1. create: UTF-8 BOM + CRLF so Windows PowerShell 5.1 reads it correctly
    machine._apply_profile_block(prof, block, dry_run=False)
    raw = prof.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert machine._B_BEGIN in raw and machine._B_END in raw
    assert b"\r\n" in raw
    assert machine._block_state(prof, want) == "current"

    # 2. idempotent: same block -> byte-identical file
    machine._apply_profile_block(prof, block, dry_run=False)
    assert prof.read_bytes() == raw

    # 3. foreign content (any encoding) is preserved byte-for-byte on append
    foreign = "Write-Host 'héllo'\n".encode("utf-16")
    prof2 = tmp_path / "foreign.ps1"
    prof2.write_bytes(foreign)
    machine._apply_profile_block(prof2, block, dry_run=False)
    out = prof2.read_bytes()
    assert out.startswith(foreign)
    assert out.endswith(want)

    # 4. stale block is replaced inside the markers only
    block2 = machine._block_content({"zoxide": "if (2) { }"})
    machine._apply_profile_block(prof2, block2, dry_run=False)
    out2 = prof2.read_bytes()
    assert out2.startswith(foreign)  # user bytes untouched
    assert machine._block_state(prof2, machine._block_bytes(block2)) == "current"
    assert machine._block_state(prof2, want) == "stale"


def test_block_state_missing(tmp_path):
    assert machine._block_state(tmp_path / "nope.ps1", b"x") == "missing"
    plain = tmp_path / "plain.ps1"
    plain.write_bytes(b"Write-Host 'no markers'\n")
    assert machine._block_state(plain, b"x") == "missing"


# ------------------------------------------------------------- posix block

def test_posix_block_upsert(tmp_path, monkeypatch):
    monkeypatch.setattr(machine.Path, "home", classmethod(lambda cls: tmp_path))
    root = tmp_path / "ws"
    ms = {"env_vars": {"AGENT_WORKSPACE_ROOT": "{root}"},
          "path_entries": ["{root}/scripts"]}

    machine._apply_posix(root, ms, dry_run=False)
    prof = tmp_path / ".profile"
    text = prof.read_text(encoding="utf-8")
    assert f'export AGENT_WORKSPACE_ROOT="{root}"' in text
    assert 'export PATH="$PATH:' in text

    machine._apply_posix(root, ms, dry_run=False)
    assert prof.read_text(encoding="utf-8") == text  # idempotent replacement


# --------------------------------------------------------------- dispatch

def test_apply_machine_setup_empty_section_is_noop(tmp_path):
    assert machine.apply_machine_setup(tmp_path, make_cfg({})) == []
    assert machine.apply_machine_setup(tmp_path, make_cfg({"env_vars": {}}), True) == []


# ------------------------------------------------------------------ status

def test_status_happy_and_drift(tmp_path, fake_reg, monkeypatch):
    root = tmp_path / "ws"
    prof = tmp_path / "prof.ps1"
    block = machine._block_content({"zoxide": "x"})
    prof.write_bytes(machine._block_bytes(block))
    monkeypatch.setattr(machine, "_powershell_profiles", lambda: [prof])
    monkeypatch.setattr(machine, "_effective_execution_policy",
                        lambda: ("RemoteSigned", "CurrentUser"))
    cfg = make_cfg({"env_vars": {"AGENT_WORKSPACE_ROOT": "{root}"},
                    "path_entries": ["{root}/scripts"],
                    "powershell": {"execution_policy": "RemoteSigned",
                                   "profile_snippets": {"zoxide": "x"}}})

    fake_reg.values["AGENT_WORKSPACE_ROOT"] = (str(root), machine._REG_SZ)
    fake_reg.values["Path"] = (str(root / "scripts"), machine._REG_SZ)
    checks = {name: ok for name, ok, _ in machine.status(root, cfg)}
    assert set(checks) == {"env", "path", "shell"}
    assert all(checks.values())

    del fake_reg.values["Path"]  # drift: PATH entry gone
    del fake_reg.values["AGENT_WORKSPACE_ROOT"]
    prof.unlink()  # drift: profile gone
    result = machine.status(root, cfg)
    checks = {name: ok for name, ok, _ in result}
    assert not any(checks.values())
    # the WARN detail must name the problems, not the healthy parts
    details = {name: detail for name, _, detail in result}
    assert "missing" in details["shell"]


def test_status_undeclared_is_empty(tmp_path):
    assert machine.status(tmp_path, make_cfg({})) == []


# ------------------------------------------------------ config integration

def test_config_layer_exposes_machine_setup(ws):
    assert build_effective(ws, "personal").machine_setup == {}

    common = ws / "configs" / "common.yaml"
    common.write_text(
        common.read_text(encoding="utf-8")
        + "machine_setup:\n  env_vars:\n    FOO: bar\n",
        encoding="utf-8",
    )
    cfg = build_effective(ws, "personal")
    assert cfg.machine_setup["env_vars"] == {"FOO": "bar"}
