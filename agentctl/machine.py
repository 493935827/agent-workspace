"""Machine-level setup: user env vars, PATH entries, PowerShell policy/profile.

Declarative source: the ``machine_setup:`` config section (common + profile +
local layers). Applied idempotently by ``agentctl bootstrap``; drift is
reported by ``agentctl doctor`` as WARN-level ``machine:*`` checks.

Windows writes ``HKCU\\Environment`` (env vars, PATH) and injects a marked
block into the PowerShell profiles; the execution policy is only ever raised
(never lowered), and Group-Policy-managed machines are left untouched.
Other platforms write a marked block into ``~/.profile``.

Two environment variables are deliberately NOT set by the shipped config:
  - ``AGENTCTL_ENV``: local.yaml is the machine marker; the variable stays a
    manual override channel (flag > variable > local.yaml).
  - ``DISABLE_TELEMETRY``: user preference, not a workspace fact (decision
    recorded 2026-10-16). Declare it under ``machine_setup.env_vars`` in
    local.yaml to opt in on a specific machine.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

try:
    import winreg
except ImportError:  # non-Windows
    winreg = None  # type: ignore[assignment]

MARK_BEGIN = "# >>> agent-workspace (machine_setup) >>>"
MARK_END = "# <<< agent-workspace (machine_setup) <<<"

_B_BEGIN = MARK_BEGIN.encode("ascii")
_B_END = MARK_END.encode("ascii")

# least -> most permissive; bootstrap only ever raises the policy
_POLICY_ORDER = ("Restricted", "AllSigned", "RemoteSigned", "Unrestricted", "Bypass")

_ENV_KEY = "Environment"
_PS_POLICY_KEY = r"Software\Microsoft\PowerShell\1\ShellIds\Microsoft.PowerShell"
_GPO_PATH = r"Software\Policies\Microsoft\Windows\PowerShell"

# registry constants usable without winreg (tests fake the store)
_HKLM = winreg.HKEY_LOCAL_MACHINE if winreg is not None else None
_HKCU = winreg.HKEY_CURRENT_USER if winreg is not None else None
_REG_SZ = 1
_REG_EXPAND_SZ = 2


# ------------------------------------------------------------------ helpers

def _resolve_value(value: str, root: Path) -> str:
    """Expand the {root} placeholder and a leading ~ (path-like values only)."""
    out = value.replace("{root}", str(root))
    if out.startswith("~"):
        out = os.path.normpath(str(Path(out).expanduser()))
    elif value.startswith("{root}"):
        out = os.path.normpath(out)
    return out


def _norm_entry(entry: str) -> str:
    """Case-insensitive, slash-normalized form for PATH comparisons."""
    return os.path.normcase(os.path.normpath(entry.strip().strip('"')))


def _rank(policy: str) -> int:
    return _POLICY_ORDER.index(policy) if policy in _POLICY_ORDER else -1


# ------------------------------------------------- user registry (Windows)

def _read_user_value(name: str) -> tuple[str, int] | None:
    """Read a value from HKCU\\Environment; None when absent."""
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _ENV_KEY, 0, winreg.KEY_READ) as k:
            value, vtype = winreg.QueryValueEx(k, name)
            return str(value), int(vtype)
    except OSError:
        return None


def _write_user_value(name: str, value: str, vtype: int) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _ENV_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, vtype, value)


def _reg_read(hive, path: str, name: str) -> str | None:
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(hive, path, 0, winreg.KEY_READ) as k:
            value, _ = winreg.QueryValueEx(k, name)
            return str(value)
    except OSError:
        return None


def _reg_write(hive, path: str, name: str, value: str) -> None:
    # CreateKey opens an existing key or creates the path; SetValueEx writes.
    with winreg.CreateKey(hive, path) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)


def _broadcast_env_change() -> None:
    """Tell running processes (Explorer -> new terminals) about HKCU changes."""
    try:
        import ctypes

        HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG = 0xFFFF, 0x1A, 0x0002
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment",
            SMTO_ABORTIFHUNG, 3000, ctypes.byref(ctypes.c_ulong()),
        )
    except Exception:  # best effort; a logoff also applies the changes
        pass


# ------------------------------------------------------------- PowerShell

def _documents_dir() -> Path:
    """The user's real Documents folder (honors OneDrive redirection)."""
    if os.name == "nt" and winreg is not None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            ) as k:
                raw, _ = winreg.QueryValueEx(k, "Personal")
            return Path(os.path.expandvars(str(raw))).expanduser()
        except OSError:
            pass
    return Path.home() / "Documents"


def _powershell_profiles() -> list[Path]:
    """Windows PowerShell 5.1 always; PowerShell 7 when installed."""
    docs = _documents_dir()
    profiles = [docs / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1"]
    if shutil.which("pwsh"):
        profiles.append(docs / "PowerShell" / "Microsoft.PowerShell_profile.ps1")
    return profiles


def _effective_execution_policy() -> tuple[str, str]:
    """(effective policy, source). Group Policy wins and is never touched."""
    for hive, source in ((_HKLM, "MachinePolicy"), (_HKCU, "UserPolicy")):
        v = _reg_read(hive, _GPO_PATH, "ExecutionPolicy")
        if v:
            return v, source
    for hive, source in ((_HKCU, "CurrentUser"), (_HKLM, "LocalMachine")):
        v = _reg_read(hive, _PS_POLICY_KEY, "ExecutionPolicy")
        if v:
            return v, source
    return "Restricted", "default"


def _ensure_execution_policy(target: str, dry_run: bool) -> str:
    current, source = _effective_execution_policy()
    if source in ("MachinePolicy", "UserPolicy"):
        return f"machine: execution policy {current} managed by {source}; left untouched"
    if _rank(target) < 0:
        return f"machine: unknown execution policy '{target}'; skipped"
    if _rank(current) >= _rank(target):
        return f"machine: execution policy already {current} (>= {target})"
    if dry_run:
        return f"[dry-run] machine: execution policy {current} -> {target} (CurrentUser)"
    _reg_write(_HKCU, _PS_POLICY_KEY, "ExecutionPolicy", target)
    return f"machine: execution policy {current} -> {target} (CurrentUser)"


# ------------------------------------------------------ marked blocks

def _block_content(snippets: dict) -> str:
    lines = [
        MARK_BEGIN,
        "# managed by agentctl machine_setup (configs/<profile>.yaml);"
        " regenerate with: agentctl bootstrap",
    ]
    for name, body in snippets.items():
        lines.append(f"# snippet: {name}")
        lines.extend(str(body).rstrip("\r\n").split("\n"))
        lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    lines.append(MARK_END)
    return "\n".join(lines)


def _block_bytes(block: str) -> bytes:
    """CRLF + UTF-8, the encoding-safe form injected into .ps1 files."""
    normalized = block.replace("\r\n", "\n")
    return normalized.replace("\n", "\r\n").encode("utf-8")


def _block_state(path: Path, want: bytes) -> str:
    """missing | current | stale for a marked block inside a file."""
    if not path.is_file():
        return "missing"
    raw = path.read_bytes()
    start, end = raw.find(_B_BEGIN), raw.find(_B_END)
    if start == -1 or end == -1 or start > end:
        return "missing"
    return "current" if raw[start:end + len(_B_END)] == want else "stale"


def _apply_profile_block(path: Path, block: str, dry_run: bool) -> str:
    """Upsert the marked block via byte surgery; user content is never decoded."""
    want = _block_bytes(block)
    raw = path.read_bytes() if path.is_file() else None

    if raw is None:
        if dry_run:
            return f"[dry-run] machine: create {path.name}"
        path.parent.mkdir(parents=True, exist_ok=True)
        # UTF-8 BOM so Windows PowerShell 5.1 reads the file as UTF-8.
        path.write_bytes(b"\xef\xbb\xbf" + want)
        return f"machine: created {path.name}"

    start, end = raw.find(_B_BEGIN), raw.find(_B_END)
    if start != -1 and end != -1 and start < end:
        end += len(_B_END)
        if raw[start:end] == want:
            return f"machine: {path.name} block already current"
        if dry_run:
            return f"[dry-run] machine: update block in {path.name}"
        path.write_bytes(raw[:start] + want + raw[end:])
        return f"machine: updated block in {path.name}"

    # existing file without markers: append, leaving every user byte intact
    if dry_run:
        return f"[dry-run] machine: append block to {path.name}"
    if raw.strip():
        tail = b"" if raw.endswith((b"\n", b"\r")) else b"\r\n"
        path.write_bytes(raw + tail + b"\r\n" + want)
    else:
        path.write_bytes(want)
    return f"machine: appended block to {path.name}"


def _text_block_state(path: Path, block: str) -> str:
    if not path.is_file():
        return "missing"
    text = path.read_text(encoding="utf-8", errors="replace")
    if MARK_BEGIN not in text or MARK_END not in text:
        return "missing"
    start = text.index(MARK_BEGIN)
    end = text.index(MARK_END) + len(MARK_END)
    return "current" if text[start:end] == block else "stale"


def _upsert_text_block(path: Path, block: str, dry_run: bool) -> str:
    text = path.read_text(encoding="utf-8") if path.is_file() else None
    if text is not None and MARK_BEGIN in text and MARK_END in text:
        start = text.index(MARK_BEGIN)
        end = text.index(MARK_END) + len(MARK_END)
        if text[start:end] == block:
            return f"machine: {path.name} block already current"
        if dry_run:
            return f"[dry-run] machine: update block in {path.name}"
        path.write_text(text[:start] + block + text[end:], encoding="utf-8")
        return f"machine: updated block in {path.name}"
    if text is None:
        if dry_run:
            return f"[dry-run] machine: create {path.name}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(block + "\n", encoding="utf-8")
        return f"machine: created {path.name}"
    if dry_run:
        return f"[dry-run] machine: append block to {path.name}"
    sep = "" if text.endswith("\n") else "\n"
    path.write_text(text + sep + "\n" + block + "\n", encoding="utf-8")
    return f"machine: appended block to {path.name}"


# ----------------------------------------------------------------- apply

def apply_machine_setup(root, cfg, dry_run: bool = False) -> list[str]:
    """Apply machine_setup idempotently; returns log lines (never raises)."""
    ms = cfg.machine_setup
    if not ms:
        return []
    try:
        if os.name == "nt":
            return _apply_windows(root, ms, dry_run)
        return _apply_posix(root, ms, dry_run)
    except OSError as e:
        return [f"FAIL machine setup: {e}"]


def _apply_windows(root: Path, ms: dict, dry_run: bool) -> list[str]:
    log: list[str] = []
    wrote = False

    # 1. user environment variables
    for name in sorted(ms.get("env_vars") or {}):
        value = _resolve_value(str((ms.get("env_vars") or {})[name]), root)
        cur = _read_user_value(name)
        if cur is not None and cur[0] == value:
            log.append(f"machine: env {name} already set")
            continue
        was = f" (was: {cur[0]})" if cur else ""
        if dry_run:
            log.append(f"[dry-run] machine: set user env {name}={value}{was}")
            continue
        try:
            _write_user_value(name, value, cur[1] if cur else _REG_SZ)
            wrote = True
            log.append(f"machine: set user env {name}={value}{was}")
        except OSError as e:
            log.append(f"FAIL set user env {name}: {e}")

    # 2. user PATH entries (append-only, order and type preserved)
    entries = [_resolve_value(str(e), root) for e in ms.get("path_entries") or []]
    if entries:
        cur = _read_user_value("Path")
        cur_value, cur_type = (cur[0], cur[1]) if cur else ("", _REG_SZ)
        existing = [e for e in cur_value.split(";") if e.strip()]
        have = {_norm_entry(e) for e in existing}
        missing = [e for e in entries if _norm_entry(e) not in have]
        if not missing:
            log.append(f"machine: user PATH ok ({len(entries)} entr"
                       f"{'y' if len(entries) == 1 else 'ies'} declared)")
        else:
            joined = ";".join(missing)
            if dry_run:
                log.append(f"[dry-run] machine: user PATH += {joined}")
            else:
                new_value = (cur_value.rstrip(";") + ";" + joined) if existing else joined
                # REG_EXPAND_SZ whenever the stored value may contain %VAR%
                new_type = _REG_EXPAND_SZ if (
                    "%" in new_value or (cur is not None and cur_type == _REG_EXPAND_SZ)
                ) else _REG_SZ
                try:
                    _write_user_value("Path", new_value, new_type)
                    wrote = True
                    log.append(f"machine: user PATH += {joined}")
                except OSError as e:
                    log.append(f"FAIL update user PATH: {e}")

    # 3. PowerShell execution policy + profile snippets
    ps = ms.get("powershell") or {}
    snippets = ps.get("profile_snippets") or {}
    if ps.get("execution_policy"):
        log.append(_ensure_execution_policy(str(ps["execution_policy"]), dry_run))
    if snippets:
        block = _block_content(snippets)
        for profile in _powershell_profiles():
            log.append(_apply_profile_block(profile, block, dry_run))

    if wrote and not dry_run:
        _broadcast_env_change()
    return log


def _posix_block(root: Path, ms: dict) -> str:
    lines: list[str] = []
    for name in sorted(ms.get("env_vars") or {}):
        value = _resolve_value(str((ms.get("env_vars") or {})[name]), root)
        lines.append(f'export {name}="{value}"')
    for entry in ms.get("path_entries") or []:
        e = _resolve_value(str(entry), root)
        lines.append(f'case ":$PATH:" in *":{e}:"*) ;; *) export PATH="$PATH:{e}" ;; esac')
    if not lines:
        return ""
    return "\n".join([MARK_BEGIN, "# managed by agentctl machine_setup"] + lines + [MARK_END])


def _apply_posix(root: Path, ms: dict, dry_run: bool) -> list[str]:
    log: list[str] = []
    if ms.get("powershell"):
        log.append("machine: powershell settings ignored on this platform")
    block = _posix_block(root, ms)
    if block:
        log.append(_upsert_text_block(Path.home() / ".profile", block, dry_run))
    return log


# ---------------------------------------------------------------- status

def status(root, cfg) -> list[tuple[str, bool, str]]:
    """(check-name, ok, detail) triples for doctor; empty when undeclared."""
    ms = cfg.machine_setup
    if not ms:
        return []
    out: list[tuple[str, bool, str]] = []

    if os.name == "nt":
        env_vars = {n: _resolve_value(str(v), root)
                    for n, v in (ms.get("env_vars") or {}).items()}
        if env_vars:
            bad = []
            for name, value in sorted(env_vars.items()):
                cur = _read_user_value(name)
                if cur is None or cur[0] != value:
                    bad.append(name)
            out.append(("env", not bad,
                        "all set" if not bad else "missing/wrong: " + ", ".join(bad)))

        entries = [_resolve_value(str(e), root) for e in ms.get("path_entries") or []]
        if entries:
            cur = _read_user_value("Path")
            have = {_norm_entry(e) for e in ((cur[0] if cur else "").split(";")) if e.strip()}
            missing = [e for e in entries if _norm_entry(e) not in have]
            out.append(("path", not missing,
                        f"{len(entries)}/{len(entries)} entries present"
                        if not missing else "missing: " + ", ".join(missing)))

        ps = ms.get("powershell") or {}
        if ps.get("execution_policy") or ps.get("profile_snippets"):
            good, bad = [], []
            if ps.get("execution_policy"):
                target = str(ps["execution_policy"])
                current, source = _effective_execution_policy()
                if source in ("MachinePolicy", "UserPolicy"):
                    good.append(f"policy {current} ({source})")
                elif _rank(current) >= _rank(target):
                    good.append(f"policy {current}")
                else:
                    bad.append(f"policy {current} < {target}")
            if ps.get("profile_snippets"):
                want = _block_bytes(_block_content(ps["profile_snippets"]))
                for profile in _powershell_profiles():
                    st = _block_state(profile, want)
                    (good if st == "current" else bad).append(
                        f"profile {profile.parent.name} {st}")
            out.append(("shell", not bad, "; ".join(bad or good)))
    else:
        block = _posix_block(root, ms)
        if block:
            st = _text_block_state(Path.home() / ".profile", block)
            out.append(("profile", st == "current", f"~/.profile block {st}"))

    return out
