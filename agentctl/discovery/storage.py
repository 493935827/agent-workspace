"""Validated local state and comment-preserving optimistic file transactions."""
from __future__ import annotations

import io
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from agentctl.bundle import SECRET_PATTERNS

from .model import DiscoveryError, ProviderResult, Resource, declarations, provider_name, resource_id, safe_text


def read_bytes(path: Path) -> bytes | None:
    return path.read_bytes() if path.exists() else None


def load_yaml(content: bytes | None):
    from ruamel.yaml import YAML
    yaml = YAML()
    yaml.preserve_quotes = True
    data = yaml.load(content.decode("utf-8-sig")) if content else {}
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise DiscoveryError("invalid-config")
    return data


def dump_yaml(data: dict) -> bytes:
    from ruamel.yaml import YAML
    stream = io.StringIO()
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.dump(data, stream)
    return stream.getvalue().encode("utf-8")


@contextmanager
def transaction(root: Path):
    """Serialize agentctl writers; arbitrary editor changes checked separately."""
    state = root / ".agentctl"
    state.mkdir(exist_ok=True)
    lock = state / "write.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise DiscoveryError("write-locked") from None
    try:
        os.close(fd)
        yield
    finally:
        lock.unlink()


def atomic_write(root: Path, path: Path, content: bytes, expected: bytes | None,
                 watched: dict[Path, bytes | None] | None = None, backup: bool = False):
    with transaction(root):
        check = dict(watched or {})
        check[path] = expected

        def verify():
            if any(read_bytes(p) != original for p, original in check.items()):
                raise DiscoveryError("concurrent-modification")

        verify()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=".agentctl-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if backup and expected is not None:
                folder = root / ".agentctl" / "backups"
                folder.mkdir(exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                (folder / f"{path.stem}-{stamp}-{uuid.uuid4().hex}.yaml").write_bytes(expected)
            verify()
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)


def snapshot_path(root: Path) -> Path:
    return root / ".agentctl" / "state" / "current.json"


def load_snapshot(root: Path) -> list[ProviderResult] | None:
    content = read_bytes(snapshot_path(root))
    if content is None:
        return None
    data = json.loads(content)
    if data.get("schema_version") != 1 or not isinstance(data.get("providers"), list):
        raise DiscoveryError("invalid-snapshot")
    results = []
    for item in data["providers"]:
        name = provider_name(item["provider"])
        status = item["status"]
        if status not in {"success", "unavailable"}:
            raise DiscoveryError("invalid-snapshot")
        scope = safe_text(item["scope"], r"[a-f0-9]{64}") if status == "success" else None
        resources = [Resource(**r) for r in item["resources"]]
        if (any(r.provider != name for r in resources) or (resources and status != "success")
                or len({r.key for r in resources}) != len(resources)):
            raise DiscoveryError("invalid-snapshot")
        results.append(ProviderResult(name, status, scope, resources))
    if len({p.provider for p in results}) != len(results):
        raise DiscoveryError("invalid-snapshot")
    return results


def save_snapshot(root: Path, results: list[ProviderResult], expected: bytes | None, dry_run: bool = False):
    if any(r.status == "error" for r in results):
        raise DiscoveryError("snapshot-incomplete")
    content = json.dumps({"schema_version": 1,
                          "saved_at": datetime.now(timezone.utc).isoformat(),
                          "providers": [p.to_dict() for p in results]}, indent=2).encode()
    if not dry_run:
        atomic_write(root, snapshot_path(root), content, expected)


def ignore_path(root: Path) -> Path:
    return root / ".agentctl" / "ignore.yaml"


def load_ignore(root: Path) -> set[tuple[str, str]]:
    data = load_yaml(read_bytes(ignore_path(root)))
    if not isinstance(data.get("ignored", []), list):
        raise DiscoveryError("invalid-ignore")
    result = set()
    for item in data.get("ignored", []):
        provider = provider_name(item["provider"])
        result.add((provider, resource_id(provider, item["id"])))
    return result


def save_ignore(root: Path, ignored: set, expected: bytes | None, dry_run: bool = False):
    content = dump_yaml({"ignored": [{"provider": p, "id": i} for p, i in sorted(ignored)]})
    if not dry_run:
        atomic_write(root, ignore_path(root), content, expected)


def adopt(root: Path, profile: str, resources: list[Resource], pin: bool, dry_run: bool) -> dict:
    from agentctl.config import merge

    safe_text(profile, r"[A-Za-z0-9_-]+", 80)
    if profile == "local":
        raise DiscoveryError("invalid-profile")
    common = root / "configs" / "common.yaml"
    target = root / "configs" / f"{profile}.yaml"
    if not target.is_file():
        raise DiscoveryError("unknown-profile")
    paths = {common, target, root / "local.yaml"}
    watched = {p: read_bytes(p) for p in paths}
    documents = {p: load_yaml(b) for p, b in watched.items()}
    # A shared profile accidentally containing a recognizable credential must
    # not be copied into the backup area as a side effect of adoption.
    if any(rx.search((watched[target] or b"").decode("utf-8-sig")) for rx, _ in SECRET_PATTERNS):
        raise DiscoveryError("unsafe-shared-config")
    shared = documents[common] if target == common else merge(documents[common], documents[target])
    existing = declarations(shared)
    pending = [r for r in resources if r.key not in existing]
    if any(r.source == "unknown" or (pin and r.version is None) for r in pending):
        raise DiscoveryError("adopt-insufficient-evidence")
    data = documents[target]
    for r in pending:
        data.setdefault("resources", {}).setdefault(r.provider, {})[r.id] = {"version": r.version if pin else None}
    content = dump_yaml(data)
    declarations(load_yaml(content))  # validate the exact bytes about to replace the file
    shared_after = data if target == common else merge(documents[common], data)
    effective = declarations(merge(shared_after, documents[root / "local.yaml"]))
    overrides = [{"provider": r.provider, "id": r.id, "effective_version": effective[r.key]}
                 for r in pending if effective[r.key] != (r.version if pin else None)]
    if pending and not dry_run:
        atomic_write(root, target, content, watched[target], watched, backup=True)
    return {"adopted": [r.to_dict() for r in pending], "local_overrides": overrides,
            "dry_run": dry_run, "profile": profile}
