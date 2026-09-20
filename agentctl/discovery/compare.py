"""Current compliance is independent of changes since the saved baseline."""
from __future__ import annotations

from collections import Counter

from .model import ProviderResult


def compare(desired: dict, results: list[ProviderResult], previous: list[ProviderResult] | None = None,
            ignored: set[tuple[str, str]] | None = None) -> list[dict]:
    current = {r.provider: r for r in results}
    baseline = {r.provider: r for r in previous or []}
    observed = {r.key: r for p in results for r in p.resources}
    old = {r.key: r for p in previous or [] for r in p.resources}
    rows = []
    for key in sorted(set(desired) | set(observed) | set(old)):
        provider, name = key
        result, before = current.get(provider), baseline.get(provider)
        resource, past = observed.get(key), old.get(key)
        declared = key in desired
        if not result or result.status != "success":
            status = "INDETERMINATE"
        elif not resource:
            status = "MISSING" if declared else "ABSENT"
        elif declared:
            wanted = desired[key]
            status = ("MATCH" if wanted is None else "INDETERMINATE" if resource.version is None
                      else "MATCH" if wanted == resource.version else "DRIFT")
        else:
            status = "UNKNOWN" if resource.source == "unknown" else "NEW"
        comparable = (result and before and result.status == before.status == "success"
                      and result.scope == before.scope)
        history = "NO_BASELINE" if previous is None else "INCOMPARABLE"
        if comparable:
            if resource and not past:
                history = "RESTORED" if declared else "APPEARED"
            elif past and not resource:
                history = "DISAPPEARED"
            elif resource and past:
                history = ("INCOMPARABLE" if resource.version is None or past.version is None
                           else "VERSION_CHANGED" if resource.version != past.version else "UNCHANGED")
            else:
                history = "UNCHANGED"
        rows.append({"provider": provider, "id": name, "status": status,
                     "declared": declared, "desired_version": desired.get(key),
                     "observed_version": resource.version if resource else None,
                     "source": resource.source if resource else None,
                     "ignored": not declared and key in (ignored or set()), "history": history})
    return rows


def summary(rows: list[dict]) -> dict:
    return dict(sorted(Counter(row["status"] for row in rows).items()))


def exit_code(results: list[ProviderResult], rows: list[dict], check: bool = False) -> int:
    if any(r.status == "error" for r in results):
        return 2
    if check:
        if any(r["declared"] and r["status"] == "INDETERMINATE" for r in rows):
            return 2
        if any(r["declared"] and r["status"] in {"MISSING", "DRIFT"} for r in rows):
            return 1
    return 0
