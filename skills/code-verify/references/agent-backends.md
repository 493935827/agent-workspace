# Agent Backends for Stage 1 AI Review

code-verify separates **deterministic validation logic** (`scripts/code_verify.py`,
agent-neutral) from **the agent runtime that performs semantic review**. The
official Anthropic review workflow (`references/review-workflow.md`) is the
shared prompt; a backend is whatever executes it. Adding a new agent later
must not require changing the workflow or the core script.

## Backend contract

A backend receives:

- `isolation_dir` — a detached git worktree containing exactly the staged
  tree. It MUST be used as the working directory for all review activity.
- `prompt_path` — the filled `review-workflow.md` (placeholders already
  replaced, project rules injected).
- `result_path` — where the final JSON verdict must be written.

A backend must:

1. Execute the workflow's steps (pre-check, CLAUDE.md collection, summary,
   parallel reviewers, independent verification, filtering) using its own
   native agent/subagent capabilities. "haiku / sonnet / opus agent" in the
   workflow are role hints (light / standard / strongest reviewer); each
   backend maps them to its own model or agent policy.
2. Enforce read-only review: no backend agent may modify files under
   `isolation_dir`.
3. Produce exactly one JSON object matching the schema in
   `review-workflow.md` step 7, written to `result_path` (or captured from
   stdout for one-shot CLIs).
4. Fail closed: any backend failure (missing CLI, spawn error, timeout,
   unparseable output) yields verdict `ERROR`, never `PASS`.

## Built-in backends

### `dsh` (default when run by a DSH agent)

The running DSH agent executes the workflow itself:

1. `python code_verify.py static --prepare --backend dsh` — prepares
   isolation + prompt, prints `{"state": "ai-review-required", ...}`.
2. The agent reads `prompt_path` and orchestrates it with native subagent
   tools (`subagent` / `subagent_fork`), one child per workflow step; the
   haiku pre-check (step 1) may run inline when it needs no tools.
3. The agent assembles the final JSON and writes it to `result_path`.
4. `python code_verify.py static --ai-result <result_path>` — validates the
   staged tree is unchanged, finalizes record and reports.

### `claude-code` (fully unattended)

`code_verify.py` spawns `claude -p --output-format json` (Claude Code ≥ 2.x
headless) with cwd = isolation dir, pre-approved read-only tools
(Read/Grep/Glob/Task/TodoWrite + read-only `git diff/log/show/status`
Bash patterns) and Edit/Write/WebFetch/WebSearch disallowed. The final text
must be the workflow's JSON object. Model role words map through the
runtime's own `ANTHROPIC_*` model configuration.

## Configuration

Target repository `.code-verify/config.json`:

```json
{ "ai_backend": "auto" }
```

- `"auto"` — `claude-code` when the `claude` CLI resolves on PATH, else
  `dsh`. The `dsh` fallback still requires the agent in the loop
  (prepare → AI review → finalize); an unattended `all` run that resolves
  to `dsh` refuses with instructions instead of producing any verdict
  (no default PASS either way).
- Explicit `"dsh"` / `"claude-code"` pins the backend. Callers may override
  per run with `--backend`. `static --prepare` works with every backend:
  it writes the prompt + pending record and exits without any AI call.

## Adding a new backend (codex, ...)

1. Add a launcher that satisfies the contract above (spawn the agent CLI, or
   hand the workflow to a human-driven agent session and collect
   `result_path`).
2. Register it in `code_verify.py` `AI_BACKENDS` (a small dispatch entry) and
   document the model-role mapping here.
3. Extend `scripts/install_skill.py` `TARGETS` with the agent's skill
   directory so the skill installs into that runtime.
4. Do not fork the workflow prompt or the core script.
