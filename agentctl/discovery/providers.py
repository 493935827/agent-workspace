"""Provider adapters. Only query commands; raw results never leave this module."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .model import DiscoveryError, ProviderResult, Resource, resource_id


@dataclass(frozen=True)
class Provider:
    executable: str
    args: tuple[str, ...]
    scope_args: tuple[str, ...] = ()


PROVIDERS = {
    "winget": Provider("winget", ("list", "--disable-interactivity")),
    "uv": Provider("uv", ("tool", "list", "--show-version-specifiers", "--offline", "--color", "never"),
                   ("tool", "dir", "--offline")),
    "pipx": Provider("pipx", ("list", "--json"), ("environment", "--value", "PIPX_HOME")),
    "npm": Provider("npm", ("list", "--global", "--depth=0", "--long", "--json", "--offline"),
                    ("root", "--global")),
    "pnpm": Provider("pnpm", ("list", "--global", "--depth=0", "--json", "--long"),
                     ("root", "--global")),
    "vscode": Provider("code", ("--list-extensions", "--show-versions")),
}
QUICK = ("uv", "pipx", "npm", "pnpm", "vscode")


class QueryError(Exception):
    def __init__(self, category: str, code: int | None = None):
        self.category, self.code = category, code


def query(executable: str, args: tuple[str, ...], cwd: Path) -> str:
    env = dict(os.environ, NO_COLOR="1", UV_OFFLINE="1", PIP_NO_INPUT="1",
               PIP_DISABLE_PIP_VERSION_CHECK="1", NPM_CONFIG_UPDATE_NOTIFIER="false",
               NPM_CONFIG_AUDIT="false", NPM_CONFIG_FUND="false",
               CI="1", PAGER="cat")
    try:
        proc = subprocess.run([executable, *args], cwd=cwd, env=env,
                              stdin=subprocess.DEVNULL, capture_output=True,
                              timeout=45,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except subprocess.TimeoutExpired:
        raise QueryError("timeout") from None
    except OSError:
        raise QueryError("execution") from None
    if proc.returncode:
        raise QueryError("exit", proc.returncode)
    if len(proc.stdout) > 8_000_000:
        raise QueryError("output-limit")
    try:
        return proc.stdout.decode("utf-8-sig")
    except UnicodeError:
        raise QueryError("encoding") from None


def _registry_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return (parsed.scheme == "https" and parsed.hostname in {"registry.npmjs.org", "registry.npmmirror.com"}
            and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment)


def parse_node(provider: str, text: str) -> list[Resource]:
    data = json.loads(text)
    if provider == "pnpm":
        if not isinstance(data, list) or len(data) > 1:
            raise DiscoveryError("parse")
        data = data[0] if data else {}
    if not isinstance(data, dict) or data.get("error") or data.get("problems"):
        raise DiscoveryError("parse")
    deps = data.get("dependencies", {})
    if not isinstance(deps, dict):
        raise DiscoveryError("parse")
    out = []
    for name, spec in deps.items():
        if not isinstance(spec, dict) or spec.get("missing") or spec.get("invalid"):
            raise DiscoveryError("parse")
        resolved = spec.get("resolved", spec.get("_resolved"))
        # URLs and local links are never persisted. Missing provenance stays UNKNOWN.
        known = _registry_url(resolved) and not spec.get("link")
        out.append(Resource(provider, name, spec.get("version"), "registry" if known else "unknown"))
    return out


def parse_pipx(text: str) -> list[Resource]:
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("venvs"), dict):
        raise DiscoveryError("parse")
    out = []
    for item in data["venvs"].values():
        pkg = item["metadata"]["main_package"]
        name = pkg["package"]
        requested = pkg.get("package_or_url", "")
        known = (isinstance(requested, str) and re.fullmatch(
            re.escape(name) + r"(?:\[[A-Za-z0-9_,.-]+\])?(?:(?:==|>=|<=|~=|>|<)[0-9][A-Za-z0-9_.+,<>=!~-]*)?", requested, re.I)
            and not pkg.get("editable") and not pkg.get("pip_args"))
        out.append(Resource("pipx", name, pkg.get("package_version"), "registry" if known else "unknown"))
    return out


def parse_uv(text: str) -> list[Resource]:
    if not text.strip() or text.strip() == "No tools installed":
        return []
    out = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith("- ") and out:
            continue  # executable names are not resource IDs
        match = re.fullmatch(r"([A-Za-z0-9_.-]+) v([^ ]+)(?: (.*))?", line)
        if not match:
            raise DiscoveryError("parse")
        name, ver, requested = match.groups()
        # --show-version-specifiers makes direct URL requirements visible.
        known = not requested or bool(re.fullmatch(r"\[required: [A-Za-z0-9_.<>=!~*, -]+\]", requested))
        out.append(Resource("uv", name, ver, "registry" if known else "unknown"))
    return out


def parse_vscode(text: str) -> list[Resource]:
    out = []
    for line in text.splitlines():
        if not line.strip():
            continue
        name, sep, ver = line.strip().rpartition("@")
        if not sep:
            raise DiscoveryError("parse")
        out.append(Resource("vscode", name, ver, "editor"))
    return out


def parse_winget(text: str) -> list[Resource]:
    # Winget has no stable JSON list interface. Fail closed on truncated or
    # unrecognized tables, so partial parsing can never manufacture MISSING.
    lines = text.splitlines()
    separators = [i for i, line in enumerate(lines) if re.fullmatch(r"-{5,}", line.strip())]
    if len(separators) != 1:
        raise DiscoveryError("parse")
    separator = separators[0]
    if separator == 0:
        raise DiscoveryError("parse")
    def width(value):
        return sum(2 if unicodedata.east_asian_width(c) in {"W", "F"} else 1 for c in value)

    header = lines[separator - 1]
    starts = [width(header[:m.start()]) for m in re.finditer(r"\S+", header)]
    if len(starts) not in {3, 4, 5}:
        raise DiscoveryError("parse")

    def cells(line):
        # Windows table padding counts wide CJK glyphs as two screen columns.
        expanded = "".join(c + ("\0" if width(c) == 2 else "") for c in line)
        bounds = starts + [len(expanded)]
        return [expanded[a:b].replace("\0", "").strip() for a, b in zip(bounds, bounds[1:])]

    out = []
    for line in lines[separators[0] + 1:]:
        if not line.strip():
            continue
        columns = cells(line)
        if len(columns) < 3 or len(columns) > 5:
            raise DiscoveryError("parse")
        _, name, ver, *rest = columns
        if re.fullmatch(r"[<>]=?\s+[0-9][A-Za-z0-9_.+!-]*", ver):
            ver = None  # Winget sometimes reports an approximate version bound.
        source = rest[-1] if rest and rest[-1] in {"winget", "msstore"} else "unknown"
        if "…" in name or "..." in name:
            raise DiscoveryError("parse")
        if source == "unknown":
            try:
                resource_id("winget", name)
            except DiscoveryError:
                name = "unmanaged-" + hashlib.sha256(name.encode()).hexdigest()[:24]
        out.append(Resource("winget", name, ver, source))
    return out


def discover(provider: str, cwd: Path) -> ProviderResult:
    spec = PROVIDERS[provider]
    executable = shutil.which(spec.executable)
    if not executable or (provider == "winget" and os.name != "nt"):
        return ProviderResult(provider, "unavailable")
    try:
        location = query(executable, spec.scope_args, cwd).strip() if spec.scope_args else "default-instance"
        if not location or "\n" in location:
            raise DiscoveryError("scope")
        # Fingerprint paths and identity, never reveal host paths or env values.
        context = [provider, str(Path(executable).resolve()), location,
                   str(Path.home()), os.environ.get("COMPUTERNAME", os.uname().nodename if os.name != "nt" else ""),
                   *[os.environ.get(k, "") for k in ("VSCODE_PORTABLE", "XDG_CONFIG_HOME", "APPDATA", "NPM_CONFIG_PREFIX")]]
        scope = hashlib.sha256(json.dumps(context).encode()).hexdigest()
        text = query(executable, spec.args, cwd)
        parsers = {"uv": parse_uv, "pipx": parse_pipx, "vscode": parse_vscode, "winget": parse_winget}
        resources = parse_node(provider, text) if provider in {"npm", "pnpm"} else parsers[provider](text)
        # Several installed instances may share the agreed (provider, id)
        # identity. Presence is reliable; conflicting exact versions are not.
        grouped = {}
        for resource in resources:
            previous = grouped.get(resource.key)
            if previous:
                resource = Resource(provider, resource.id,
                                    resource.version if previous.version == resource.version else None,
                                    resource.source if previous.source == resource.source else "unknown")
            grouped[resource.key] = resource
        return ProviderResult(provider, "success", scope, sorted(grouped.values(), key=lambda r: r.id))
    except QueryError as exc:
        return ProviderResult(provider, "error", error=exc.category, exit_code=exc.code)
    except (DiscoveryError, ValueError, KeyError, TypeError, AttributeError):
        return ProviderResult(provider, "error", error="parse")


def scan(providers: list[str] | tuple[str, ...], cwd: Path) -> list[ProviderResult]:
    return [discover(name, cwd) for name in providers]
