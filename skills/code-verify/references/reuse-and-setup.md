# code-verify Reuse Matrix, Provenance, and Target-Repository Setup

## Reuse matrix (verified against this machine, 2026 local check)

| Function | Source | Action |
|---|---|---|
| Agent runtime, subagents, tool calling | Claude Code CLI 2.1.296 (installed) **and** DSH native `subagent` tools | Reuse (pluggable backend, see agent-backends.md) |
| Code review workflow / prompt framework | Anthropic official plugin `code-review` (`commands/code-review.md`) | Reuse, minimal-diff adapted (`references/review-workflow.md`) |
| Independent issue verification + high-signal filtering | Same official workflow steps 5-6 | Reuse verbatim |
| Confidence filtering ("only HIGH SIGNAL issues" + false-positive list) | Same official workflow | Reuse verbatim |
| Target test runner | The repo's own validation framework via `target.command` | Reuse (adapter = config only) |
| Staged diff / snapshot identity | git plumbing: `git write-tree`, `git diff --cached`, `commit-tree`, `worktree add` | Implemented in `code_verify.py` (the real gap) |
| Validation record + commit gate | `.git/code-verify/records` + `gate` | Implemented (the real gap) |
| Pre-commit hook | git native `pre-commit` + `core.hooksPath` | Implemented thin shim (the real gap) |
| Reports | `report.json`/`report.md` generated from records | Implemented thin adapter |

Not rebuilt: agent scheduler, subagent context isolation, review prompt
framework, issue dedup, PR-free workflow (no gh dependency anywhere).

## Provenance / license

- Upstream: <https://github.com/anthropics/claude-plugins-official>
  `plugins/code-review/commands/code-review.md`, pinned commit
  `a7ba5b93db0c7c8d17f3f1d25853adca79598a1a` (main, 2026-10-30).
- License: Apache-2.0 (plugin LICENSE). Keep the upstream notice when
  redistributing; the adapted prompt preserves the upstream structure and
  documents its diff in the header comment.
- Local marketplace snapshot already present at
  `~/.claude/plugins/marketplaces/claude-plugins-official/plugins/code-review`.

### Upstream → adaptation diff (kept minimal)

| Upstream | code-verify adaptation |
|---|---|
| Input: GitHub PR via `gh pr view/diff` | Input: staged diff via `git diff --cached`; agents' cwd = isolated staged-tree worktree |
| Pre-check: PR closed/draft/already-reviewed | Empty-diff/trivial pre-check kept; "already reviewed" becomes a deterministic record lookup (`gate`) |
| Steps 2-4: CLAUDE.md collection, summary, 4 parallel reviewers | Kept; added reviewer 5 (firmware validation rules) |
| Step 5-6: per-issue verification, filtering | Kept; unverifiable device/timing findings route to `risks` (REVIEW_REQUIRED) instead of being dropped |
| Step 7: terminal summary | Final message must be one JSON verdict object (schema in the prompt) |
| Steps 8-9: GitHub inline comments | Removed (local report files instead) |
| `allowed-tools` gh/MCP frontmatter | Not applicable headless; enforced by `--allowedTools/--disallowedTools` in the claude-code backend |

### Upgrade compatibility notes

- The adaptation pins no Claude Code internals; it consumes the documented
  headless surface (`-p`, `--output-format json`, `--allowedTools`). If the
  upstream prompt changes, re-diff `commands/code-review.md` against the
  header comment of `references/review-workflow.md` and port only the delta.
- `code_verify.py` depends on stable git plumbing only (`write-tree`,
  `commit-tree`, `worktree`), not porcelain output formats.

## Target repository setup (firmware repo)

1. Install the skill (user level or project level):

   ```
   python scripts/install_skill.py --project D:\path\to\fw-repo
   ```

2. Create `.code-verify/config.json` in the repo:

   ```json
   {
     "ai_backend": "auto",
     "claude_bin": "claude",
     "review_rules": "generic",
     "static_commands": [["python", "-m", "ruff", "check", "."]],
     "static_timeout_sec": 900,
     "claude_timeout_sec": 1800,
     "target": {
       "kind": "real",
       "target_id": "INTEGRATION-01",
       "command": ["python", "tools/run_integration.py", "--suite", "smoke"],
       "timeout_sec": 1800,
       "release_command": [],
       "junit_xml": null
     },
     "artifacts": ["build/app.bin"],
     "test_config_files": ["tests/target_config.yaml"]
   }
   ```

   - `target.command` MUST be the repo's existing validation entry point;
     code-verify never invents target commands. Anything with side effects
     (flashing, resets, database migrations, network calls) belongs inside
     that command, authorized by the repo owner — the skill never adds them.
   - `kind: "mock"` is for development/automated tests only; the commit gate
     rejects mock PASS records.
   - `artifacts` (build outputs), `test_config_files` and the whole `target`
     block are fingerprinted; changing any of them after target validation
     invalidates the record.
   - `junit_xml` is resolved relative to the isolated snapshot worktree
     root: the target command must write it inside that worktree (relative
     path), not into the main checkout.
   - `review_rules` picks the Stage 1 ruleset: bundled `generic` (default)
     or `firmware-board`, or a repo-relative path to your own rules file.

3. Install the gate hook (refuses foreign hook managers and foreign hooks):

   ```
   python <path-to-skill>/scripts/code_verify.py --repo-root . install-hook
   ```

   or run it from the skill. It sets `core.hooksPath=.code-verify/hooks` only
   when unset, copies the core script into `.git/code-verify/`, and ignores
   `.code-verify/` via `.git/info/exclude` (no tracked files touched).
   Re-running `install-hook` is idempotent and is the supported way to
   refresh the script copy after a skill update: an existing `pre-commit`
   that is byte-identical to the code-verify shim is refreshed in place,
   while a foreign hook file (or a foreign `core.hooksPath` manager) is
   still refused. Worktrees: records live in
   the shared git common dir, so a linked worktree shares validation records;
   the hook shim resolves the script through `git rev-parse --git-common-dir`.

4. Commit flow from now on: stage → `static` → `target` → `gate` (the hook
   runs it automatically) → commit. The hook never runs AI or hardware work;
   it only checks the record for the current staged tree.

5. Housekeeping: isolated snapshot worktrees persist under
   `<git-common-dir>/code-verify/work/<tree>/` so reports stay reproducible.
   When a tree is finally merged or abandoned, clean its worktree up with
   `git worktree remove --force <path>` followed by `git worktree prune`.
