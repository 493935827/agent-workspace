---
name: run-tickets
description: "Run a Matt Pocock /to-tickets set in Codex as dependency-aware waves from a local ticket directory or a GitHub parent issue. Use only when the user explicitly invokes /run-tickets and authorizes branches, worktrees, commits, and fresh implementation subagents."
disable-model-invocation: true
---

# Run Tickets

Run an implementation queue as a control-plane orchestrator. Keep the tracker as the state source; keep each implementation in one fresh worker context.

## Input and capability check

Accept `/run-tickets <ticket-set> [--parallel N] [--scheduler rolling|barrier]`. Default to `rolling`; accept `barrier` only as an explicit compatibility/safety choice. Treat `<ticket-set>` as exactly one of:

- a local feature directory containing `issues/`, or the `issues/` directory itself; local `/to-tickets` output normally lives at `.scratch/<feature>/issues/<NN>-<slug>.md`;
- a GitHub parent issue as `#123` when the repository is unambiguous, `owner/repo#123`, or a full `github.com/owner/repo/issues/123` URL.

For a GitHub parent issue, use the configured tracker workflow in `docs/agents/issue-tracker.md`. Prefer the connected GitHub app for issue data; use authenticated `gh` only for capabilities the connector lacks. Read `references/github-tracker.md` before resolving a GitHub set. Load the parent, its open child tickets, each ticket body/comments, labels, assignee, and native dependency state. If child-ticket membership or dependencies cannot be read reliably, stop before dispatch rather than treating all repository issues as the batch.

Clamp `N` to `1..3`; default to `3`. Before changing Git state, inspect `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING`, project docs, CI, package/build files, and the installed `to-tickets`, `implement`, `tdd`, and `code-review` skills. Discover repository validation and commit conventions from those sources; do not hard-code an ecosystem.

Use Codex's multi-agent and Git worktree capabilities only when they are available. If either required capability is unavailable, stop before dispatch and explain the missing capability. Do not substitute shared working-tree workers.

For a local set, run the helper before every dispatch/reconciliation:

```powershell
python "$env:USERPROFILE\.agents\skills\run-tickets\scripts\ticket_graph.py" <ticket-set> --format json
```

The helper understands the local template (`# 01 — title`, `**Blocked by:**`, `**Status:**`) and reports validation errors, cycles, deterministic frontier order, and blocked tickets. Read `references/local-tracker.md` when a local tracker file differs from this format or status reconciliation is needed. For GitHub, query the live tracker again at equivalent points; GitHub's issue/dependency state replaces this helper.

## Preflight

1. Resolve the ticket set and parse every ticket. Stop before dispatch for duplicate IDs, unknown blockers, self dependencies, or a cycle; show the cycle path. In GitHub mode, the parent issue is the batch map and its ticket children are the complete ticket set; do not include unrelated repository issues.
2. Inspect `git status --short`, active worktrees, branches, and the current branch. If uncommitted work cannot clearly be attributed to this batch, stop. Never stash, reset, clean, force-push, rewrite published history, delete unknown branches, or merge into the default branch.
3. Run one shared worktree bootstrap before dispatch. Validate the repository's declared runtime (for example Python), test runner and required plugins (including `pytest-timeout` for pytest), DLL/native dependencies, non-sensitive test fixtures, Git ignore rules, GUI availability when relevant (for example Tk), and declared build/release tools (for example PyInstaller). Detect credential-like files without printing their contents. If bootstrap fails, stop once with the actionable cause; do not let every worker rediscover it. Install a missing project-declared test plugin only when the repository's dependency workflow makes that an ordinary, scoped setup step; otherwise report it as a preflight failure.
4. Record baseline verification when feasible. Distinguish pre-existing failures from ticket regressions. Classify verification into `worker_targeted`, `integration_sensitive`, `unattended_test_repair`, and `release_full`; keep the concrete commands in the dispatch brief rather than assuming every ticket runs every check.
5. During functional work, preflight the release toolchain read-only: tool version, spec/config parse, required DLLs, build-directory creation, smoke arguments, output-name collision, and free disk space. Do not produce the final release artifact early.
6. Choose or create one integration branch from the explicit current baseline, following repository naming conventions. A reasonable fallback is `task/<feature-slug>`. Do not merge it to `main`/`master`.
7. Reconcile existing `in-progress` tickets before planning a new wave. If a ticket commit is already integrated and verified, mark it done/close the GitHub issue. If a completed ticket branch awaits integration, resume integration. Preserve an uncommitted recovery worktree and assign a new, fresh recovery worker. If the state is ambiguous, park it and report it; do not guess.

## Rolling scheduler

Repeat until no runnable ticket remains and no worker is running. Keep at most `MAX_IMPLEMENTATION_CONCURRENCY = 3` active implementation workers. A completed, failed, or question worker releases its agent slot immediately after its compact result has been recorded; it must not occupy capacity while integration or reconciliation continues.

1. Re-read the tracker and, for a local set, run the helper after every worker result and every integration. A ticket is runnable only when it is neither done, in-progress, failed, needs-info, nor integration-conflict, and every blocker is **done and integrated**. In GitHub mode, an open issue with an open native blocker or fallback `Blocked by:` issue is not runnable; a closed issue is only treated as completed after its integration evidence is confirmed.
2. Rank the runnable frontier before each dispatch. Honor explicit tracker priority first. Otherwise prefer the dependency critical path: high downstream-dependent count, membership in the longest remaining dependency chain, lower estimated complexity, lower historical failure risk, and lower conflict risk with active workers. Estimate complexity from acceptance-criterion count, files/surfaces involved, state-machine/concurrency/transaction work, build/GUI needs, and prior worker failures. Use numeric ID, tracker order, then filename only as deterministic tie-breakers. For a ready set where 05/06/07 unlock more work than 02/03, select 05/06/07.
3. Scan ticket scope and known changed files conservatively. Serialize only clear semantic conflicts involving a shared schema, migration, core API contract, package manifest, shared configuration, or central router. Purely mechanical overlap may run concurrently if integration can remain local. If such a semantic conflict makes safe rolling dispatch unclear, enter a full `barrier` interval for the affected set: wait, integrate, verify, then resume rolling. `--scheduler barrier` uses this behavior for every batch.
4. On each completed worker, immediately record its result, release its slot, and integrate a successful commit before dispatching a replacement. Use the latest integration `HEAD` as `integration_base` for every newly dispatched worktree; never dispatch a replacement from a stale base. Integrate one commit at a time, inspect the result, run its stated `integration_sensitive` checks, and mark the ticket **done** only after those checks pass. Record tracker completion metadata (and GitHub commit/verification/close actions) at that point. Keep failed/question/conflicted tickets non-done and retain their evidence.
5. Recompute the frontier after that integration/reconciliation. If a runnable ticket has no semantic/file conflict with every still-running worker, create its branch and independent worktree from the current integration `HEAD`, mark it in-progress, and dispatch a fresh worker to refill the free slot. Do not reuse or fork an earlier implementation context; do not make the orchestrator a fourth worker. In barrier mode, defer replacements until all selected workers finish.
6. Run `unattended_test_repair` as soon as enough integrated work makes it useful; repair its failures before release, using fresh scoped workers when necessary. Run `release_full` only after every ticket is integrated: clean release build, final default/full tests, performance tests when declared, and smoke checks.
7. Finish with `SUCCESS` only when every ticket is done and integrated; otherwise report `PARTIAL COMPLETION`, completed IDs, failed/needs-info/conflicted IDs, blocked dependents, preserved worktrees, and user decisions needed.

## Worker contract

Give each fresh worker only its ticket, relevant parent-spec excerpt, integrated blockers, integration-base SHA, repository rules, branch/worktree path, scope boundary, and the explicit validation matrix: `worker_targeted` commands it must run; `integration_sensitive` commands the orchestrator will run after cherry-pick; and `release_full` commands reserved for the release stage. The worker must:

1. Inspect only the necessary repository area and implement exactly that ticket. Record a minimal adjacent blocker fix; turn other discoveries into follow-ups.
2. Apply the `/implement` discipline directly: use TDD where an agreed seam exists; run only its `worker_targeted` checks during work; review acceptance criteria, scope, regressions, safety, compatibility, artifacts, and dead code; fix must-fix findings. Do not broaden this to every repository test/typecheck/lint/build unless that command is explicitly in `worker_targeted`.
3. Use a bounded command for every test, GUI, build, or smoke action. For pytest, prefer `python -m pytest <target> --timeout=30 --timeout-method=thread --durations=20`; use 60 seconds only for declared performance checks. Use an equivalent repository-native timeout where pytest is not the runner. Never start an unbounded GUI or full suite.
4. If work lasts longer than five minutes, emit a compact structured heartbeat at most once per five minutes and whenever phase changes; do not include reasoning or logs. Every `current_check` has its own timeout:

```text
heartbeat:
ticket: <ID>
phase: inspect | red | green | review | commit
elapsed: <duration>
current_check: <bounded command or none>
last_completed_check: <check/result or none>
blocked: <yes/no and short reason>
```

5. Write non-authoritative telemetry events to a JSONL file under the OS temporary directory only. Record only `worker_started`, `red_confirmed`, `heartbeat`, `worker_done`, and the orchestrator's `integrated` events with ticket and timestamp. Exclude reasoning, source code, credentials, and repository paths; keep the tracker as the sole state source and keep telemetry out of Git.
6. Commit one scoped change following repository convention. Operate only in its assigned branch/worktree; never switch or merge the integration/sibling branches.
7. Return no transcript, only:

```text
status: done | failed | question
ticket: <ID>
branch: <branch>
worktree: <path>
commit: <SHA or none>
summary: <1–4 bullets>
verification: <passed/failed/skipped checks and reason>
review: <must-fix status>
followups: <items or none>
question: <decision or none>
```

For an ordinary local failure, allow one retry only, and make it another fresh worker. A second failure becomes `failed`. For a genuine product, architecture, breaking-API, data-deletion, or security-policy decision, consult the ticket/spec/ADRs/conventions first. If still undecided, mark `needs-info`, preserve the worktree, and continue unrelated tickets.

## Integration and recovery

Resolve mechanical conflicts only when the resolution is clearly local (for example imports or independent config additions), then re-run verification. Mark semantic business/API/schema/migration conflicts `integration-conflict`, preserve their branch/worktree, and leave dependents blocked.

Never infer completion from worker success alone. The lifecycle is `ready → in-progress → worker-done → integrating → done`; `done` means implemented, reviewed, verified, integrated, and integration-verified. On rerun, use the tracker plus Git evidence to skip completed tickets and resume only recoverable work. Do not create an authoritative sidecar state file.

## User-facing progress

Report compactly: loaded count, validation result, integration branch, concurrency, wave ticket IDs, worker/integration outcomes, verification summary, and final branch state. Omit full logs, worker reasoning, and large diffs.
