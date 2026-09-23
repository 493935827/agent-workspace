---
name: define-bounded-goal
description: Define or refine a concrete, measurable Goal with an explicit wall-clock timebox, work depth, verification ceiling, safe-stop rules, and structured handoff.
---

# Define Bounded Goal

## Overview

Shape the user's intent into an objective an agent can pursue honestly, then add an execution budget contract. Prefer measurable outcomes, explicit evidence, bounded scope, and a safe stopping state over activity descriptions.

This skill is derived from OpenAI's curated `define-goal` skill. It preserves that skill's goal workflow and quality bar while adding bounded execution. The stage-boundary budget check is informed by the general check-before-execute pattern in the third-party `token-budget` skill; framework-specific convoy, mayor, polecat, and TypeScript state machinery is not part of this skill.

Use this skill only when the user explicitly invokes `$define-bounded-goal`. It defines or refines a goal and, when the request also authorizes implementation, governs that bounded execution. It does not create durable snapshots, ledgers, decision logs, resume files, or framework-specific state.

## Workflow

1. Confirm that goal definition is needed.
   - Use this skill because the user explicitly invoked `$define-bounded-goal` to define, refine, create, or execute a bounded Goal.
   - Only call Goal tools when the user explicitly asks to create or track a Goal. A request to word or refine an objective does not itself authorize `create_goal`.

2. Restate the likely goal in concrete terms.
   A usable goal names:
   - the specific outcome that will be true
   - the main artifact, system, repo, environment, or user-facing behavior involved
   - how completion will be verified
   - what is in scope
   - what is out of scope when ambiguity would matter
   - the stop condition for asking the user instead of grinding

3. Make it quantitative when the domain supports it.
   Prefer numbers that represent real success, not decorative precision:
   - pass/fail validators: exact tests, checks, CI jobs, evals, commands, or acceptance criteria
   - quality thresholds: latency, error rate, cost, accuracy, recall, precision, coverage, flake rate, bundle size, memory, uptime, completion rate, or manual review criteria
   - artifact constraints: file paths, affected modules, allowed commands, output formats, target environments, deadlines, or maximum blast radius
   - evidence counts: number of reproduced failures, successful reruns, reviewed examples, migrated records, addressed comments, or verified cases

4. Repair weak goals before setting them.
   - Rewrite vague goals into measurable objectives when local context makes the rewrite safe.
   - Ask one concise clarification question when the missing detail changes the intended outcome or validation.
   - Reject pure activity goals such as "make progress," "keep investigating," "improve things," or "work on X" unless they are sharpened into a verifiable outcome.

5. Form the Budget Contract after the concrete goal is clear.
   - Read the user's `time_budget`, `depth`, `verification`, `allowed_scope`, `excluded_work`, `command_timeout`, and `retry_limit`.
   - Require `time_budget` before implementation. If it is absent, help the user complete the contract and stop before changing the implementation.
   - Use the defaults and mappings in [Budget Contract](#budget-contract) for fields the user omitted.
   - State the resulting contract in one concise commentary update so the user can immediately correct a misunderstanding.
   - Append the contract to the objective. Include at least the wall-clock timebox, depth, verification ceiling, allowed scope, and stopping conditions.
   - Treat the timebox as covering exploration, implementation, verification, and final handoff together.

6. Check active Goal state before creating a Goal.
   - Call `get_goal`.
   - If there is no active Goal and the objective meets the quality bar, call `create_goal`.
   - If an active Goal still matches the user's intent, continue using it instead of creating a duplicate.
   - If an active Goal conflicts with the new request, ask whether to finish the current Goal, mark it complete if done, or start a separate Goal-backed task.

7. Create the Goal only after it passes the quality bar.
   - Use a single concise objective string containing both the measurable goal and Budget Contract.
   - Include verification evidence and scope bounds in the objective.
   - Pass `token_budget` only when the user explicitly supplied a token count. Never infer or convert a token budget from task size or time.
   - Do not call `create_goal` for ordinary multi-step work unless the user explicitly asked for Goal-backed work.

8. If implementation is authorized, execute within the contract.
   - At each stage or tool-call boundary, apply [Budget Checkpoints](#budget-checkpoints).
   - Keep the working state safe and explainable at every checkpoint.
   - End with [Structured Handoff](#structured-handoff), whether the goal completes early or execution stops at a bound.

## Budget Contract

Use these fields:

| Field | Meaning | Default |
|---|---|---|
| `time_budget` | Wall-clock limit from exploration through final handoff | Required before implementation |
| `depth` | `probe`, `minimal`, `standard`, or `release` | `minimal`, subject to the time-only recommendation below |
| `verification` | `syntax`, `targeted`, `affected`, or `full` | Map from depth |
| `allowed_scope` | Modules, directories, or files that may be read or changed | Smallest scope directly implicated by the goal |
| `excluded_work` | Work explicitly deferred this run | Empty; high-cost and separately authorized work remains bounded below |
| `command_timeout` | Wait limit for one ordinary command | `min(60 seconds, 20% of time_budget)` |
| `retry_limit` | Maximum retries after the first failure for the same cause | `1` |

`time_budget` is a soft wall-clock timebox. Avoid starting work expected to exceed the remaining budget, but do not promise millisecond-precise termination of every external process.

Verification levels are ceilings, not work quotas:

- `syntax`: the cheapest relevant parser, lint, type, or compile check.
- `targeted`: syntax/compile plus 1–3 directly relevant tests or equivalent focused evidence.
- `affected`: targeted checks plus the affected suite that fits the budget.
- `full`: explicitly relevant release checks or a complete regression run when authorized and feasible.

Map depth to work and verification as follows:

| Depth | Allowed work | Default verification ceiling |
|---|---|---|
| `probe` | Read-only exploration and feasibility judgment; leave version-controlled files unchanged | `targeted`, limited to fast read-only evidence that directly answers the question |
| `minimal` | Smallest vertical slice implementing the core behavior; omit opportunistic refactors, documentation expansion, and exhaustive environment coverage | `targeted` |
| `standard` | User-visible behavior, necessary error paths, and focused regression coverage | `affected` |
| `release` | Migration, compatibility, failure recovery, delivery documentation, and release checks that the user authorized | `full` or the explicitly listed release checks |

When the user supplies only a time budget, these are recommended scope ceilings, not targets to consume:

| Time budget | Recommended depth | Recommended verification |
|---:|---|---|
| 5–10 minutes | `minimal` | Syntax check and the most relevant test |
| 10–30 minutes | `standard` | Targeted tests |
| 30–60 minutes | `standard` | Affected suite within budget |
| More than 60 minutes | `standard` | Enter `release` or full regression only when explicit |

A longer budget never upgrades `standard` to `release`. Full regression, PyInstaller or other release packaging, and release smoke checks are candidates only under `release` or when the user explicitly requests them. HIL, Flash/eFuse, production deployment, real external writes, and long-running performance tests always require separate authorization; `release` alone does not authorize them.

If the remaining budget cannot accommodate a safe minimal change, downgrade to `probe`: leave no partial implementation, deliver the evidence collected, and identify the next independent slice.

## Budget Checkpoints

Check at stage and tool-call boundaries rather than trying to meter every reasoning action. Natural checkpoints are the end of exploration, completion of one atomic edit, return of a long command, and entry into the final 20% of the timebox.

Before a costly stage or command:

1. Estimate whether it can finish within the remaining time.
2. Reserve at least 20% of total time for verification and handoff, plus 10% for one failure or fallback.
3. If the work does not fit, shrink it to an independently deliverable slice. If no safe slice exists, stop implementation and hand off.
4. Once the same failure cause reaches `retry_limit`, preserve its evidence and stop repeating that attempt.
5. Do not start a test, build, search, package, or other command expected to exceed `command_timeout` or the remaining budget.

During the final 20%, freeze scope. Finish only the current atomic edit when safe, run the fastest relevant verification, and prepare the handoff.

Use one of these fixed stop reasons:

| `stop_reason` | Condition | Response |
|---|---|---|
| `completed_early` | Goal and contracted verification are complete with time remaining | End immediately; do not seek extra work |
| `time_budget_warning` | Remaining time entered the final 20% | Freeze scope, verify, and hand off |
| `time_budget_exhausted` | Timebox ended or the next safe action no longer fits | Finish only an immediately closable atomic operation, then stop |
| `token_budget_exhausted` | Goal tooling reports the token budget exhausted | Stop according to Goal state and report it |
| `command_timeout` | An external command reached its wait limit | Preserve output and choose at most one smaller alternative check |
| `retry_limit_reached` | The same cause reached the retry limit | Report evidence and the blocker; stop blind retries |
| `scope_expansion_required` | The next step needs broader scope, permission, or external authorization | Request the new authorization instead of widening the goal |
| `unsafe_to_continue` | Source, data, or hardware state cannot remain explainable within budget | Stop new actions and state the exact current condition |

At a bounded stop, preserve user changes and maintain an explainable state. Never use destructive Git cleanup, discard existing work, or describe a budget stop as full completion.

## Goal Quality Bar

Before `create_goal`, the objective should answer:

- What concrete thing will be true when this is done?
- What evidence will prove it?
- What quantitative or binary threshold defines success?
- What scope boundaries matter?
- What should cause the agent to stop and ask?
- Is the wall-clock timebox explicit?
- Are work depth and verification ceiling explicit?
- Are high-cost activities that will not run automatically identified?
- Can execution stop at the bound without damaging or discarding the user's existing changes?

Good:

> Within 20 minutes, implement the smallest server-side change that reduces checkout API p95 below 250 ms on the documented slow path, at `minimal` depth and `targeted` verification, limited to the checkout handler and its direct tests. Verify with `npm run test:checkout` and the existing local benchmark for 3 consecutive runs; exclude full regression and deployment, stop after one retry for the same failure, and preserve an explainable working tree at the timebox.

Good:

> Within 15 minutes, resolve code-change review comments on PR 123 at `standard` depth, touching only affected auth files and tests. Verify with targeted auth tests and, if budget remains, the affected suite; exclude release packaging and production writes, and stop for authorization if broader scope is required.

Weak:

> Make checkout faster for a while.

Weak:

> Keep investigating the PR comments until time runs out.

## Quantification Heuristics

- For bugs, define success as reproduction first, fix second, and a failing-then-passing validator when possible.
- For tests, name the exact command and required pass condition.
- For performance, name the metric, target threshold, measurement method, and number of runs.
- For quality work, define an observable acceptance bar such as reviewed examples, lint/typecheck/test pass, or user-approved artifact.
- For research, define the decision the research must enable, the sources or systems in scope, and the evidence standard.
- For operations, define healthy state, monitoring window, failure threshold, and rollback or escalation trigger.

## Clarifying Questions

Ask only when a reasonable rewrite would risk pursuing the wrong outcome. Keep the question short and oriented around the missing validator, scope boundary, or required timebox.

Useful question shapes:

- "What wall-clock timebox should cover exploration, implementation, verification, and handoff?"
- "What metric should define success here: latency, cost, accuracy, or user-visible behavior?"
- "Which environment should I verify against: local, staging, or production?"
- "What is the minimum evidence you want before I mark this goal complete?"

If the user cannot provide a metric, propose the most honest binary validator available and ask for confirmation. If the user does not provide a timebox, complete only the Budget Contract and do not start implementation.

## Structured Handoff

End every bounded execution with this exact field structure:

```text
Budget: <time_budget>; depth=<depth>; verification=<verification>
Stop reason: <stop_reason>
Completed: <smallest verified result actually completed>
Verified: <checks actually run and their results>
Deferred: <work omitted because of budget, depth, scope, or authorization>
Current state: <whether it runs and whether changes or external processes remain unverified>
Next slice: <smallest independent slice for a subsequent run>
```

Use `completed_early` and end immediately when the goal and contracted verification finish before the budget. When time expires, say explicitly that execution stopped at the timebox; do not use "mostly complete" to conceal omitted regression, packaging, or hardware checks.
