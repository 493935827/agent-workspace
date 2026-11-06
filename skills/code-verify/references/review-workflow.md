<!--
Adapted review prompt for code-verify Stage 1 (static review).

PROVENANCE (do not lose this):
- Derived from the Anthropic official plugin:
  https://github.com/anthropics/claude-plugins-official
  plugins/code-review/commands/code-review.md
  Pinned commit: a7ba5b93db0c7c8d17f3f1d25853adca79598a1a (main, 2026-10-30)
  License: Apache-2.0 (see reuse-and-setup.md)
- Minimal-diff adaptation for LOCAL STAGED CHANGES instead of a GitHub PR.
  Kept: pre-check gate, CLAUDE.md collection, change summary, 4 parallel
  review agents, per-issue independent verification, high-signal filtering,
  false-positive list.
  Removed: gh pr view/diff/comment, PR closed/draft/already-reviewed checks
  (handled deterministically by code_verify.py record lookup), GitHub inline
  comments (steps 8-9 of the original), GitHub link format requirements.
  Added: 5th "project validation rules" agent + REVIEW_REQUIRED risk channel.

code_verify.py fills the placeholders {{CHANGED_FILES}}, {{CHANGE_CONTEXT}}
and {{PROJECT_RULES}}, then hands this file to one pluggable AGENT BACKEND
(see references/agent-backends.md):

- `dsh`: the running DSH agent executes this workflow itself, using its
  native subagent tools for the per-step agents, and writes the final JSON
  to the result path.
- `claude-code`: piped to `claude -p` with cwd set to the isolated snapshot
  worktree; the model role words (haiku / sonnet / opus) map through the
  runtime's own model configuration.
- future backends (codex, ...): see agent-backends.md for the contract.

Do not edit placeholders by hand.
-->

Provide a code review for the staged changes of the current repository.

You are reviewing code that is staged for commit. Your working directory is an
isolated checkout of exactly the staged tree, so Read/Grep/Glob/git commands
see precisely the code that will be committed. History is available for
context. There is NO pull request.

**Agent assumptions (applies to all agents and subagents):**
- All tools are functional and will work without error. Do not test tools or
  make exploratory calls. Make sure this is clear to every subagent that is
  launched.
- Only call a tool if it is required to complete the task. Every tool call
  should have a clear purpose.
- No agent may modify any file. Review is read-only.

The staged change intent provided by the author is:

<change_context>
{{CHANGE_CONTEXT}}
</change_context>

The changed files are:

<changed_files>
{{CHANGED_FILES}}
</changed_files>

To do this, follow these steps precisely:

1. Launch a haiku agent to check if any of the following are true:
   - The staged diff is empty (nothing to review).
   - The change is trivial and obviously correct (e.g. whitespace, version
     bump with no logic change), based only on the diff and changed files.

   If the staged diff is empty, stop and emit the final JSON with
   verdict "PASS" and an empty findings list. Otherwise proceed.

2. Launch a haiku agent to return a list of file paths (not their contents)
   for all relevant CLAUDE.md files including:
   - The root CLAUDE.md file, if it exists
   - Any CLAUDE.md files in directories containing files modified by the
     staged changes

3. Launch a sonnet agent to examine the staged changes and return a summary
   of the changes. It may use `git diff --cached` and `git log` for history
   context.

4. Launch 5 agents in parallel to independently review the changes. Each
   agent should return the list of issues, where each issue includes a
   description and the reason it was flagged (e.g. "CLAUDE.md adherence",
   "bug", "validation-rules"). The agents should do the following:

   Agents 1 + 2: CLAUDE.md compliance sonnet agents
   Audit changes for CLAUDE.md compliance in parallel. Note: When evaluating
   CLAUDE.md compliance for a file, you should only consider CLAUDE.md files
   that share a file path with the file or parents.

   Agent 3: Opus bug agent (parallel with agents 4 and 5)
   Scan for obvious bugs. Focus only on the diff itself without reading extra
   context. Flag only significant bugs; ignore nitpicks and likely false
   positives. Do not flag issues that you cannot validate without looking at
   context outside of the git diff.

   Agent 4: Opus bug agent (parallel with agents 3 and 5)
   Look for problems that exist in the introduced code. This could be
   security issues, incorrect logic, etc. Only look for issues that fall
   within the changed code.

   Agent 5: Project validation rules agent (parallel with agents 3 and 4)
   Review the changed code against the project validation rules below. These
   rules describe how test/validation code can produce wrong PASS/FAIL
   verdicts or damage test credibility. Flag only issues grounded in the
   changed code.

   <project_validation_rules>
   {{PROJECT_RULES}}
   </project_validation_rules>

   **CRITICAL: We only want HIGH SIGNAL issues.** Flag issues where:
   - The code will fail to compile or parse (syntax errors, type errors,
     missing imports, unresolved references)
   - The code will definitely produce wrong results regardless of inputs
     (clear logic errors)
   - Clear, unambiguous CLAUDE.md violations where you can quote the exact
     rule being broken
   - Clear violations of the project validation rules above, where the
     violating code path is visible in the diff

   Do NOT flag:
   - Code style or quality concerns
   - Potential issues that depend on specific inputs or state
   - Subjective suggestions or improvements

   If you are not certain an issue is real, do not flag it. False positives
   erode trust and waste reviewer time.

   In addition to the above, each subagent should be told the change context
   above. This will help provide context regarding the author's intent.

5. For each issue found in the previous step by agents 3, 4 and 5, launch
   parallel subagents to validate the issue. These subagents should get the
   change context along with a description of the issue. The agent's job is
   to review the issue to validate that the stated issue is truly an issue
   with high confidence. For example, if an issue such as "variable is not
   defined" was flagged, the subagent's job would be to validate that is
   actually true in the code. Another example would be CLAUDE.md issues. The
   agent should validate that the CLAUDE.md rule that was violated is scoped
   for this file and is actually violated. Use Opus subagents for bugs and
   logic issues, and sonnet agents for CLAUDE.md violations.

   For validation-rule issues whose truth CANNOT be established statically
   because it depends on runtime state, timing, ordering, external services,
   or the execution environment, do NOT drop them silently and do
   NOT confirm them blindly. Instead reclassify them as RISKS: move them to
   the "risks" output list with the matching reason (device-state, timing,
   hardware-dependency, or environment) and a concrete note of what must be
   checked during target validation (`what_to_check_on_target`).

6. Filter out any issue that was not validated in step 5. This step will
   give us our list of high signal issues for the review. Risks from step 5
   are kept in their own list and never count as confirmed findings.

7. Output the review as a single JSON object and nothing else (no markdown
   fence, no commentary before or after). Use exactly this schema:

   {
     "verdict": "PASS" | "FAIL" | "REVIEW_REQUIRED" | "ERROR",
     "summary": "one short paragraph",
     "findings": [
       {
         "id": "F1",
         "file": "path/relative/to/repo",
         "line": 42,
         "severity": "blocker" | "major" | "minor",
         "category": "bug" | "validation-rules" | "claude-md",
         "description": "what is wrong",
         "trigger_condition": "when does this misbehave",
         "evidence": "quoted code or quoted rule",
         "suggested_fix": "how to fix",
         "verified": true
       }
     ],
     "risks": [
       {
         "id": "R1",
         "file": "path",
         "line": 42,
         "reason": "device-state" | "timing" | "hardware-dependency" | "environment",
         "description": "what cannot be proven statically",
         "what_to_check_on_target": "concrete target validation check"
       }
     ],
     "claude_md_files": ["list of consulted CLAUDE.md paths"],
     "notes": "anything else reviewers should know"
   }

   Verdict rules:
   - Any confirmed finding with severity "blocker" -> "FAIL".
   - No confirmed findings and no risks -> "PASS".
   - No confirmed blocker but at least one risk -> "REVIEW_REQUIRED".
   - Confirmed non-blocker findings without risks -> "FAIL" is not required;
     use "REVIEW_REQUIRED" so a human decides. A human always decides for
     non-blockers.

Use this list when evaluating issues in Steps 4 and 5 (these are false
positives, do NOT flag):

- Pre-existing issues
- Something that appears to be a bug but is actually correct
- Pedantic nitpicks that a senior engineer would not flag
- Issues that a linter will catch (do not run the linter to verify)
- General code quality concerns (e.g. lack of test coverage, general security
  issues) unless explicitly required in CLAUDE.md
- Issues mentioned in CLAUDE.md but explicitly silenced in the code (e.g.
  via a lint ignore comment)

Notes:

- Do not use web fetch. Everything needed is in the working directory.
- Create a todo list before starting.
- Every finding must cite file and line. Every CLAUDE.md finding must quote
  the exact rule.
- If the review itself cannot be completed (tool failures, unreadable
  state), emit verdict "ERROR" with an explanation in "notes". Never emit
  "PASS" when the review did not complete.
