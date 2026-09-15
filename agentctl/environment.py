"""Which environment is this machine? CLI flag > AGENTCTL_ENV > local.yaml."""
from __future__ import annotations

import os
from pathlib import Path

from agentctl.config import available_profiles, profile_path

LOCAL_FILE = "local.yaml"


class EnvError(RuntimeError):
    pass


def local_path(root: Path) -> Path:
    return root / LOCAL_FILE


def read_local(root: Path) -> dict:
    import yaml  # lazy

    p = local_path(root)
    if not p.is_file():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise EnvError(f"Invalid YAML in {p}: {e}") from e
    if not isinstance(data, dict):
        raise EnvError(f"{p} must contain a mapping")
    return data


def validate_environment(root: Path, env: str) -> None:
    if not profile_path(root, env).is_file():
        avail = ", ".join(available_profiles(root)) or "none"
        raise EnvError(f"Unknown environment '{env}'. Available profiles: {avail}")


def resolve(root: Path, cli_env: str | None = None) -> tuple[str, str]:
    """Return (environment, source). Raise EnvError when nothing is set."""
    if cli_env:
        validate_environment(root, cli_env)
        return cli_env, "--env"
    var = os.environ.get("AGENTCTL_ENV")
    if var:
        validate_environment(root, var)
        return var, "AGENTCTL_ENV"
    env = read_local(root).get("environment")
    if env:
        validate_environment(root, str(env))
        return str(env), "local.yaml"
    raise EnvError(
        "Environment is not set for this machine. "
        "Run: agentctl bootstrap --env personal|company|intranet"
    )


def set_environment(root: Path, env: str, dry_run: bool = False) -> bool:
    """Persist the environment marker into local.yaml. True if changed."""
    import yaml  # lazy

    validate_environment(root, env)
    local = read_local(root)
    if local.get("environment") == env:
        return False
    local["environment"] = env
    if dry_run:
        return True
    with open(local_path(root), "w", encoding="utf-8") as f:
        yaml.safe_dump(local, f, sort_keys=False, allow_unicode=True)
    return True