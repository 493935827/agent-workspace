"""Environment profiles and the layered merge that builds the effective config.

Effective Config = common + one environment profile + local.yaml (machine layer).

Merge rules:
  - dict  : recursive merge
  - list  : union preserving order (deduplicated), EXCEPT keys listed in
            REPLACE_LIST_KEYS, which are replaced wholesale -- those keys
            describe machine-specific paths and unioning them across layers
            would re-add paths a machine explicitly tried to override
  - scalar: the higher layer wins
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_DIR = "configs"
COMMON = "common"

# lists that merge by REPLACEMENT instead of union
REPLACE_LIST_KEYS = {"targets"}


class ConfigError(RuntimeError):
    pass


def _load_yaml(path: Path) -> dict:
    import yaml  # lazy: lets the CLI print a helpful error without PyYAML

    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {path}: {e}") from e
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"Expected a mapping at the top level of {path}")
    return data


def merge(base: Any, override: Any, _key: str = "") -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for k, v in override.items():
            out[k] = merge(out[k], v, _key=k) if k in out else v
        return out
    if isinstance(base, list) and isinstance(override, list) and _key not in REPLACE_LIST_KEYS:
        out = list(base)
        for item in override:
            if item not in out:
                out.append(item)
        return out
    return override


def config_dir(root: Path) -> Path:
    return root / CONFIG_DIR


def available_profiles(root: Path) -> list[str]:
    d = config_dir(root)
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.yaml") if p.stem not in (COMMON, "local"))


def profile_path(root: Path, name: str) -> Path:
    return config_dir(root) / f"{name}.yaml"


@dataclass
class EffectiveConfig:
    environment: str | None
    raw: dict = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)

    @property
    def skills(self) -> list[str]:
        return list(self.raw.get("skills") or [])

    @property
    def exclude_skills(self) -> list[str]:
        return list(self.raw.get("exclude_skills") or [])

    @property
    def enabled_skills(self) -> list[str]:
        excluded = set(self.exclude_skills)
        seen, out = set(), []
        for s in self.skills:
            if s not in excluded and s not in seen:
                seen.add(s)
                out.append(s)
        return out

    @property
    def links(self) -> dict:
        return self.raw.get("links") or {}

    @property
    def tools(self) -> dict:
        return self.raw.get("tools") or {}

    @property
    def required_secrets(self) -> list[str]:
        return list((self.raw.get("secrets") or {}).get("required") or [])

    @property
    def optional_secrets(self) -> list[str]:
        return list((self.raw.get("secrets") or {}).get("optional") or [])

    @property
    def internet(self) -> bool:
        return bool((self.raw.get("network") or {}).get("internet", True))


def build_effective(
    root: Path, environment: str | None, extra_local: dict | None = None
) -> EffectiveConfig:
    """common + <environment profile> + local.yaml machine layer."""
    raw = _load_yaml(profile_path(root, COMMON))
    sources = [f"{CONFIG_DIR}/{COMMON}.yaml"]

    if environment and environment != COMMON:
        raw = merge(raw, _load_yaml(profile_path(root, environment)))
        sources.append(f"{CONFIG_DIR}/{environment}.yaml")

    local_file = root / "local.yaml"
    local_layer: dict = {}
    if local_file.is_file():
        local_layer = _load_yaml(local_file)
        local_layer.pop("environment", None)  # marker, not config
        sources.append("local.yaml")
    if extra_local:
        local_layer = merge(local_layer, extra_local)
    if local_layer:
        raw = merge(raw, local_layer)

    return EffectiveConfig(environment=environment, raw=raw, sources=sources)