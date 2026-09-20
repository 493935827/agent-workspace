"""Small, validated values shared by discovery, storage and comparison."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from agentctl.bundle import SECRET_PATTERNS


class DiscoveryError(RuntimeError):
    """Messages are fixed categories, never external command/config contents."""


def safe_text(value: object, pattern: str, limit: int = 200) -> str:
    if (not isinstance(value, str) or len(value) > limit
            or not re.fullmatch(pattern, value)
            or any(rx.search(value) for rx, _ in SECRET_PATTERNS)):
        raise DiscoveryError("invalid-field")
    return value


def provider_name(value: object) -> str:
    return safe_text(value, r"[a-z][a-z0-9_-]*", 40)


def resource_id(provider: str, value: object) -> str:
    patterns = {
        "npm": r"(?:@[a-z0-9_.-]+/)?[a-z0-9][a-z0-9_.-]*",
        "pnpm": r"(?:@[a-z0-9_.-]+/)?[a-z0-9][a-z0-9_.-]*",
        "uv": r"[A-Za-z0-9][A-Za-z0-9_.-]*",
        "pipx": r"[A-Za-z0-9][A-Za-z0-9_.-]*",
        "vscode": r"[A-Za-z0-9-]+\.[A-Za-z0-9_.-]+",
    }
    result = safe_text(value, patterns.get(provider, r"[A-Za-z0-9][A-Za-z0-9_.+-]*"))
    if provider in {"uv", "pipx"}:
        return re.sub(r"[-_.]+", "-", result).lower()
    return result.lower() if provider == "vscode" else result


def version(value: object) -> str | None:
    if value is None or value in ("", "unknown", "Unknown", "未知"):
        return None
    return safe_text(value, r"[0-9][A-Za-z0-9_.+!-]*", 100)


@dataclass(frozen=True)
class Resource:
    provider: str
    id: str
    version: str | None = None
    source: str = "unknown"

    def __post_init__(self):
        object.__setattr__(self, "provider", provider_name(self.provider))
        object.__setattr__(self, "id", resource_id(self.provider, self.id))
        object.__setattr__(self, "version", version(self.version))
        if self.source not in {"registry", "winget", "msstore", "editor", "unknown"}:
            raise DiscoveryError("invalid-source")

    @property
    def key(self) -> tuple[str, str]:
        return self.provider, self.id

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProviderResult:
    provider: str
    status: str
    scope: str | None = None
    resources: list[Resource] = field(default_factory=list)
    error: str | None = None
    exit_code: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def declarations(raw: dict) -> dict[tuple[str, str], str | None]:
    result = {}
    groups = raw.get("resources", {})
    if not isinstance(groups, dict):
        raise DiscoveryError("invalid-resources")
    for provider, items in groups.items():
        provider_name(provider)
        if not isinstance(items, dict):
            raise DiscoveryError("invalid-resources")
        for name, spec in items.items():
            key = provider, resource_id(provider, name)
            if not isinstance(spec, dict) or set(spec) != {"version"} or key in result:
                raise DiscoveryError("invalid-resource-declaration")
            result[key] = version(spec["version"])
    return result
