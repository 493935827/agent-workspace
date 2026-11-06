---
name: code-verify
description: "Two-stage pre-commit validation for any repository — Stage 1 static AI review of the git staged tree (pluggable review rules + agent backends, adapted from the Anthropic official code-review workflow) plus Stage 2 target validation running the repository's own test command inside an isolated snapshot worktree, gated by a validation record that a pre-commit hook enforces. Firmware on-board testing is one bundled scenario (review_rules: firmware-board). Use when the user wants to verify staged changes before committing, asks for /code-verify, code-verify static/target/status/gate, or setting up the verification hook in a repository."
---

# code-verify

Verify the **staged tree** (git snapshot to be committed) before the commit
happens. Two stages, one snapshot, no auto commit/push ever:

```
git staged tree ──► Stage 1 static review ──PASS──► Stage 2 target validation ──PASS──► Commit Permission
     (snapshot)      deterministic tools +                  the repo's own validation
                      AI review (pluggable                   command against the isolated
                      rules & agent backend)                 snapshot; real evidence only
```

Hard invariants (never violate):

- **One snapshot**: every stage operates on the staged tree hash
  (`git write-tree`); unstaged work is never reviewed, never tested.
- **Fail-closed**: missing config, missing tool, AI failure, timeout — the
  result is ERROR/DENIED, never PASS. Only PASS unlocks the next stage.
- **No side effects without explicit user authorization**: run `target` only
  when the user asked for that validation — the target command may touch
  hardware, databases, networks, whatever the repository defined. `--dry-run`
  touches nothing and writes no PASS.
- **Mock is never a real PASS**: records from `target.kind: "mock"` are
  rejected by the gate.
- The review never modifies code under review; you never auto-commit/push.

## The two stages

- **Stage 1 — static**: deterministic commands from the config, then AI
  review of the staged diff. Review RULES are pluggable: `review_rules` in
  the config selects a bundled ruleset (`generic` by default,
  `firmware-board` for the firmware scenario) or a repo-relative rules file;
  `--rules` overrides per run.
- **Stage 2 — target**: runs the repository's own `target.command` inside
  the isolated snapshot worktree (env `CODE_VERIFY_SNAPSHOT_TREE` set),
  captures exit code and optional JUnit XML, releases via
  `target.release_command`. The target is whatever the repository defines —
  an integration suite, a simulator, a device farm, an on-board firmware
  test. `kind: "real"` means the command is authoritative evidence;
  `kind: "mock"` is for development and never grants commit permission.

## Scenarios

| Scenario | `review_rules` | `target.command` example |
|---|---|---|
| Generic software repo | `generic` (default) | integration/e2e suite, API smoke tests |
| Firmware + on-board test | `firmware-board` | flash firmware + run board test suite |
| Any other target | own rules file | whatever proves the change works |

## Running as the DSH agent (default)

Work inside the target repository.

1. Preconditions: `git rev-parse --show-toplevel` succeeds and
   `.code-verify/config.json` exists. If missing, follow
   [references/reuse-and-setup.md](references/reuse-and-setup.md) → "Target
   repository setup" and ask the user to confirm it.
2. Stage 1 — use the **dsh backend** (you are the review orchestrator):

   ```
   python scripts/code_verify.py static --prepare --backend dsh
   ```

   It prints `isolation_dir`, `prompt_path`, `result_path`. Then:

   - Read `prompt_path`. It is the adapted Anthropic official workflow;
     execute it as the orchestrator: launch each step's agent with your
     native `subagent` tool (one child per step; the step-1 empty-diff
     pre-check may run inline), always with `isolation_dir` as the children's
     working context. The haiku/sonnet/opus words are role hints (light /
     standard / strongest reviewer).
   - Assemble the final JSON object (schema is in the prompt, step 7) and
     write it to `result_path`.
   - Finalize:

     ```
     python scripts/code_verify.py static --ai-result <result_path>
     ```

   Any AI-side failure ⇒ let finalize fail (ERROR) or record verdict ERROR.
   Never fabricate a PASS.

   If the claude CLI is configured, `--backend claude-code` runs the same
   workflow unattended instead.

3. Stage 2 — only after Static Review: PASS **and** explicit user
   authorization:

   ```
   python scripts/code_verify.py target
   ```

   This runs the repository's own `target.command` inside the isolated
   snapshot worktree (env `CODE_VERIFY_SNAPSHOT_TREE` set), captures logs,
   releases via `target.release_command`. You analyze failures, but
   PASS/FAIL comes only from the command's exit code / JUnit result. If the
   staged tree changed since static review, the target run refuses — re-run
   static.

4. Show permission state:

   ```
   python scripts/code_verify.py gate      # Commit Permission: ALLOWED / DENIED + reason
   python scripts/code_verify.py status
   ```

Reports live under `<git-common-dir>/code-verify/reports/<tree>/`
(`static.md`, `target.md`, logs, `ai-review.json`). Summarize the final
verdict to the user as `Static Review: … / Target Validation: … / Commit
Permission: …` and always name the blocking reason when not allowed. Never
commit or push.

## Modes

| Request | Action |
|---|---|
| full verify | static → (target only if user authorized) |
| "static only" / --static-only | `static` only |
| "target only" / --target-only | `target` — it self-checks the static PASS record for the same tree |
| "check status" / --status | `status` then `gate` |
| "dry run" / --dry-run | `static --dry-run`, `target --dry-run` — plan only, no side effects, no PASS |
| "set up the hook" | `install-hook` (never overwrites foreign hooks/hook managers; re-running refreshes its own shim + script copy) |

## Installing into other agents

The skill is portable. Copy it into another runtime's skill directory with
`python scripts/install_skill.py --target claude-code|codex|dsh|agents|project`
(see the script's help). Backends are pluggable — to drive the review from a
different agent runtime, follow
[references/agent-backends.md](references/agent-backends.md); do not fork the
workflow prompt or the core script.

## References

- [references/review-workflow.md](references/review-workflow.md) — the
  adapted Anthropic official review prompt (provenance header documents the
  minimal diff; pinned upstream commit inside).
- [references/rules/generic.md](references/rules/generic.md) — default
  validation review rules for reviewer agent 5 (any repository).
- [references/rules/firmware-board.md](references/rules/firmware-board.md) —
  firmware/on-board scenario ruleset (extends the generic baseline).
- [references/agent-backends.md](references/agent-backends.md) — backend
  contract, dsh/claude-code details, how to add new agents.
- [references/reuse-and-setup.md](references/reuse-and-setup.md) — reuse
  matrix, versions, license, target-repo setup (`config.json`, hook).
