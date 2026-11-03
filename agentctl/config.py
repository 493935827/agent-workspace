"""Environment profiles and the layered merge that builds the effective config.

Effective Config = common + one environment profile + local.yaml (machine layer).

Merge rules:
  - null  : "not set" -- the base value is kept, never wiped (older versions
            silently erased the base subtree when a higher layer wrote null).
            One exception: a null written at a
            ``resources.<provider>.<id>.version`` leaf is the discovery
            "declared, unpinned" marker and clears the inherited pin
  - dict  : recursive merge
  - list  : union preserving order (deduplicated), EXCEPT keys whose leaf
            name is listed in REPLACE_LIST_KEYS, which are replaced
            wholesale -- those keys describe machine-specific paths and
            unioning them across layers would re-add paths a machine
            explicitly tried to override
  - scalar: the higher layer wins
  - a structured value (dict/list) merged against a scalar at the same key
    raises ConfigError with the dotted key path, instead of silently
    discarding one side; a scalar written into a list key (e.g.
    ``skills: alpha``) is exactly such a conflict and is rejected
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


def _type_name(value: Any) -> str:
    if isinstance(value, dict):
        return "mapping"
    if isinstance(value, list):
        return "list"
    return type(value).__name__


def _reject_structured_scalar_conflict(base: Any, override: Any, key_path: str) -> None:
    """A dict/list meeting a scalar at the same key is a config mistake."""
    if base is None:  # no base value: the override simply defines it
        return
    if isinstance(base, (dict, list)) != isinstance(override, (dict, list)):
        where = key_path or "<top level>"
        raise ConfigError(
            f"Config type conflict at '{where}': cannot merge "
            f"{_type_name(base)} with {_type_name(override)}. Use the same "
            f"structure in the higher layer, or null to keep the base value."
        )


def _is_unlock_leaf(key_path: str) -> bool:
    """A null at a ``resources.<provider>.<id>.version`` leaf is the
    discovery "declared, unpinned" marker (storage.adopt writes it), not an
    unset -- it must clear the inherited pin instead of keeping it."""
    return key_path.startswith("resources.") and key_path.endswith(".version")


def merge(base: Any, override: Any, _key: str = "") -> Any:
    """Merge a higher layer into a base value.

    ``_key`` carries the dotted path of the value being merged; it is used
    for REPLACE_LIST_KEYS lookup (leaf name) and error messages.
    """
    if override is None:
        if _is_unlock_leaf(_key):
            return None  # explicit "declared, unpinned": clear the pin
        return base  # null means "not set": never wipe the base value
    _reject_structured_scalar_conflict(base, override, _key)
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for k, v in override.items():
            child = f"{_key}.{k}" if _key else k
            out[k] = merge(out[k], v, _key=child) if k in out else v
        return out
    if (isinstance(base, list) and isinstance(override, list)
            and _key.rsplit(".", 1)[-1] not in REPLACE_LIST_KEYS):
        out = list(base)
        for item in override:
            if item not in out:
                out.append(item)
        return out
    return override


# keys whose value must be a list whenever present (null = unset is fine).
# Guards against a scalar mistyped into a list key (e.g. ``skills: alpha``),
# which older versions silently exploded into single characters.
LIST_SCHEMA = ("skills", "exclude_skills", "links.targets",
               "secrets.required", "secrets.optional")


def _validate_list_schema(raw: dict) -> None:
    for dotted in LIST_SCHEMA:
        node: Any = raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                node = None
                break
            node = node[part]
        if node is None or isinstance(node, list):
            continue
        raise ConfigError(
            f"'{dotted}' must be a list in the effective config, got "
            f"{_type_name(node)} ({node!r}). Write one item per line "
            f"(\"- {node}\"), or null to leave the value unset."
        )


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

    @property
    def app_configs(self) -> dict:
        return self.raw.get("app_configs") or {}

    @property
    def machine_setup(self) -> dict:
        return self.raw.get("machine_setup") or {}


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

    _validate_list_schema(raw)
    return EffectiveConfig(environment=environment, raw=raw, sources=sources)