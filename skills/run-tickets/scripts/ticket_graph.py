#!/usr/bin/env python3
"""Validate and schedule local /to-tickets Markdown ticket sets (read-only)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HEADER = re.compile(r"^#\s+(\d+)\s+[—-]\s+(.+?)\s*$", re.M)
FIELD = r"^\*\*{label}:\*\*\s*(.*?)\s*$"
ID = re.compile(r"(?<!\d)(\d+)(?!\d)")
DONE = {"done", "completed"}
INACTIVE = DONE | {"in-progress", "running", "failed", "needs-info", "question", "integration-conflict"}


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    title: str
    status: str
    blockers: tuple[str, ...]
    path: Path
    index: int


def field(text: str, label: str, default: str = "") -> str:
    match = re.search(FIELD.format(label=re.escape(label)), text, re.M | re.I)
    return match.group(1).strip() if match else default


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def parse_blockers(value: str) -> tuple[str, ...]:
    if normalized(value).startswith(("none", "—", "-")) or not value.strip():
        return ()
    return tuple(dict.fromkeys(ID.findall(value)))


def locate(path: Path) -> Path:
    if path.name.lower() == "issues":
        return path
    candidate = path / "issues"
    return candidate if candidate.is_dir() else path


def load(issue_dir: Path) -> tuple[list[Ticket], list[str]]:
    tickets: list[Ticket] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, file in enumerate(sorted(issue_dir.glob("*.md"))):
        text = file.read_text(encoding="utf-8")
        match = HEADER.search(text)
        if not match:
            errors.append(f"{file.name}: missing '# <ID> — <title>' heading")
            continue
        ticket_id, title = match.group(1), match.group(2)
        if ticket_id in seen:
            errors.append(f"duplicate ticket ID {ticket_id}: {file.name}")
            continue
        seen.add(ticket_id)
        status = normalized(field(text, "Status", "ready-for-agent"))
        tickets.append(Ticket(ticket_id, title, status, parse_blockers(field(text, "Blocked by", "None")), file, index))
    if not tickets:
        errors.append(f"no ticket Markdown files found in {issue_dir}")
    return tickets, errors


def cycle(tickets: dict[str, Ticket]) -> list[str] | None:
    active: set[str] = set(); visited: set[str] = set(); stack: list[str] = []
    def visit(node: str) -> list[str] | None:
        if node in active:
            return stack[stack.index(node):] + [node]
        if node in visited:
            return None
        visited.add(node); active.add(node); stack.append(node)
        for blocker in tickets[node].blockers:
            result = visit(blocker)
            if result:
                return result
        stack.pop(); active.remove(node)
        return None
    for item in tickets:
        result = visit(item)
        if result:
            return result
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticket_set", type=Path)
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args()
    issue_dir = locate(args.ticket_set)
    if not issue_dir.is_dir():
        print(f"ticket directory not found: {issue_dir}", file=sys.stderr)
        return 2
    items, errors = load(issue_dir)
    by_id = {item.ticket_id: item for item in items}
    for item in items:
        for blocker in item.blockers:
            if blocker not in by_id:
                errors.append(f"ticket {item.ticket_id}: unknown blocker {blocker}")
            elif blocker == item.ticket_id:
                errors.append(f"ticket {item.ticket_id}: self dependency")
    if not errors:
        found = cycle(by_id)
        if found:
            errors.append("dependency cycle: " + " -> ".join(found))
    ready: list[Ticket] = []
    blocked: dict[str, list[str]] = {}
    if not errors:
        for item in items:
            reasons = [b for b in item.blockers if by_id[b].status not in DONE]
            if item.status not in INACTIVE and not reasons:
                ready.append(item)
            elif reasons:
                blocked[item.ticket_id] = reasons
    ordered = sorted(ready, key=lambda item: (int(item.ticket_id), item.index, item.path.name.lower()))
    payload = {
        "valid": not errors,
        "issue_dir": str(issue_dir),
        "errors": errors,
        "tickets": [{"id": t.ticket_id, "title": t.title, "status": t.status, "blocked_by": list(t.blockers), "path": str(t.path)} for t in items],
        "frontier": [t.ticket_id for t in ordered],
        "blocked": blocked,
    }
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif errors:
        print("INVALID\n" + "\n".join(f"- {error}" for error in errors))
    else:
        print("VALID")
        print("frontier: " + (", ".join(payload["frontier"]) or "(none)"))
        if blocked:
            print("blocked: " + ", ".join(f"{key} <- {','.join(value)}" for key, value in blocked.items()))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
