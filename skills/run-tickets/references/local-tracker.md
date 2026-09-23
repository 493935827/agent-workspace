# Local ticket tracker

`/to-tickets` publishes one Markdown ticket per file under `.scratch/<feature>/issues/`:

```markdown
# 01 — Ticket title

**What to build:** end-to-end behavior.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Acceptance criterion
```

Use the heading number as the ticket ID. Parse `**Blocked by:**` as the dependency source, not filename order. A dependency entry may contain an ID plus title; retain only IDs that match an existing ticket. Treat `None` / `none` / `—` as no blockers.

Status normalization for a local tracker:

| Meaning | Accepted text | Write during a run |
| --- | --- | --- |
| runnable | `ready-for-agent`, `ready`, `pending` | `ready-for-agent` |
| dispatched | `in-progress`, `running` | `in-progress` |
| integrated completion | `done`, `completed` | `done` |
| terminal failure | `failed` | `failed` |
| decision required | `needs-info`, `question` | `needs-info` |
| unresolved integration | `integration-conflict` | `integration-conflict` |

Change only the status line and add only concise completion evidence compatible with the ticket file, for example:

```markdown
**Completed:** commit `abc1234`; integration verification passed.
```

The helper is intentionally read-only. Use the tracker edit as the authoritative transition after the corresponding Git evidence exists.
