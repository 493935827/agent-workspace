---
name: handoff
description: Archive the current conversation, maintain the project's progress index, and automatically commit and push task changes when Git and a remote are configured.
argument-hint: "What will the next session be used for?"
disable-model-invocation: true
---

Archive enough context for another conversation to continue the project. Use two layers: a concise current-state index and linked conversation handoffs. Write in the user's language.

## Locate and read

1. Resolve the project root from the active task and applicable project instructions. Use the current workspace root for projectless work. Ask only if multiple plausible projects remain unresolved.
2. Read applicable project rules and the current snapshot in `<project-root>/progress/progress.md` if it exists; inspect archive rows only as needed. Before editing, inspect relevant working-tree and staged changes, the current branch, upstream, and remote configuration to distinguish this conversation's work from unrelated changes and select the upload target.
3. Read earlier handoffs only when needed to resolve a specific gap, identify this conversation's existing archive, or verify a relevant decision. Do not read every archive to prepare a handoff.
4. Treat invocation arguments as the next conversation's intended focus. Preserve the overall project objective while tailoring the next actions to that focus.

## Write the conversation handoff

Create `<project-root>/progress/` on demand. Save the handoff there, not in the OS temporary directory, `work/`, or `docs/`.

- Name new archives `handoff-YYYYMMDD-HHMMSS-<short-topic>.md`, using local time and a meaningful filename-safe topic. Resolve collisions without overwriting another conversation's archive.
- Record the conversation ID or link when available. For another handoff from the same conversation, update its existing document and index row when identity can be verified; otherwise create a distinct archive rather than guessing.
- Include the current objective and scope; tasks accomplished in this conversation; implemented-but-unverified work; remaining work and concrete next actions; blockers; essential decisions and rejected approaches that would otherwise be repeated; relevant files, working-tree state, and validation evidence; retained temporary artifacts or running jobs needed for continuation.
- Include a short suggested-skills section when relevant. Suggestions do not authorize invocation; preserve any explicit-only skill requirements.
- Reference existing requirements, designs, issues, commits, diffs, and logs instead of duplicating them. Use portable project-relative paths or links relative to the document where possible.
- Redact secrets and unnecessary personal information. Report unknown or unverified state explicitly; do not infer completion from code having been written.
- Keep the archive focused on resuming work, not a transcript of the conversation.

## Maintain `progress/progress.md`

After saving the handoff, update the index. This is the authoritative entry point for current progress, with a compact historical index of conversations.

Use this shape, adapting labels to the user's language:

```markdown
# Project progress

Updated: YYYY-MM-DD HH:mm (timezone)

## Current snapshot
- Objective / current milestone:
- Completed and verified:
- Implemented but unverified / in progress:
- Blockers: none, or a short description
- Next: the next concrete action(s)

## Conversation archive
| Date / conversation | Accomplished | Handoff |
| --- | --- | --- |
| YYYY-MM-DD / short identity | One short sentence; label unverified work | [Topic](handoff-YYYYMMDD-HHMMSS-topic.md) |
```

- Rewrite the current snapshot in place: aim for at most 10 short lines. Summarize overall milestones, not just the latest conversation. Omit unsupported percentages.
- Keep one row per archived conversation, newest first, with a short accomplishment summary and a relative link to its handoff. Preserve older rows for archival lookup; update the same conversation's row instead of duplicating it.
- Keep detailed reasoning, command output, task breakdowns, and evidence in the linked handoff or their existing source. The index should answer where the project stands and what to do next without opening a handoff.
- For a long index, read the snapshot first and search or read bounded archive rows only when locating a relevant conversation. Preserve unread history when editing rather than reconstructing or truncating the file.
- Do not create parallel `status.md`, `docs/progress.md`, or a second handoff index. If such a file already exists, inspect it and reconcile relevant current state without silently deleting historical content or breaking references.

## Establish the reading entry point

Ensure the project-root `AGENTS.md` contains one concise navigation rule, updating an equivalent existing rule rather than duplicating it:

> When continuing project work, first read the current snapshot in `progress/progress.md` if present and verify it against the relevant workspace state. Read linked handoffs only when their details are needed for the current task; search the conversation index rather than loading all archives. When material progress changes, keep the existing snapshot current. When the user requests a handoff, save the conversation archive and update its index row; preserve the handoff skill's manual invocation policy.

If no project-root `AGENTS.md` exists, create a minimal one containing this rule. Preserve unrelated instructions and explicit invocation policies. Progress archives are persistent project records, not temporary files to clean up.

## Verify and automatically upload

Check that the handoff exists, the updated index links to it correctly, the snapshot agrees with known evidence, earlier archive rows are preserved, and the navigation rule points to the correct index.

Manual invocation of this skill authorizes committing the handoff and this conversation's task changes and ordinarily pushing them to the project's configured remote, including GitHub, without asking again. A current user instruction to keep work local or skip commit/push takes precedence. Use Git transport; installing or authenticating the GitHub CLI is not required when Git push already works.

1. If the project is not in a Git repository, finish the local handoff and report that upload was skipped. Do not initialize a repository or create a remote automatically. If Git exists but no remote is configured, make the scoped local commit below and report that no upload target exists.
2. Prefer the current branch's configured remote upstream. If it has none, use an explicitly configured push remote (`branch.<name>.pushRemote`, then `remote.pushDefault`), otherwise the sole configured remote, and target the same branch name with `--set-upstream`. With multiple remotes and no configured selection, detached HEAD, or a local-only upstream, finish the local handoff and ask only for the unresolved destination. Never guess a repository or publish other branches or tags.
3. Include this handoff, its index, the navigation-rule changes, and identifiable task changes from this conversation. Preserve unrelated working-tree and staged changes; stage explicit paths or isolated hunks, never the entire repository indiscriminately. If mixed changes cannot be separated reliably, retain the documents and explain the commit blocker. Honor ignore rules and exclude credentials and temporary artifacts.
4. Run validation appropriate to the actual changes; documentation-only updates need content/link checks and `git diff --cached --check`, not a full project regression. Reuse still-valid task test results. Record unfinished or unverified work accurately; do not claim it passed. If required validation is unavailable or fails, retain the local work and report the blocker instead of uploading unvalidated task changes unless the user has explicitly authorized that.
5. Commit the scoped changes with a meaningful message; skip empty commits. Inspect the outgoing commit range and push only when all outgoing work belongs to this conversation or is already authorized. Use an explicit remote and single destination branch, such as `git push <remote> HEAD:refs/heads/<destination>`, adding `--set-upstream` when appropriate. Existing authorized local commits still need pushing even if this invocation produces no new commit.
6. Confirm success from the push result; if the result is uncertain, inspect the remote branch before retrying. On authentication, network, branch-protection, or non-fast-forward errors, preserve the local commit and report the exact obstacle. Do not force push or automatically merge/rebase to bypass it. Report upload status in the reply without repeatedly editing and recommitting the archive merely to record its own commit or push result.

## Return

Return links to the index and this conversation's handoff, the local commit ID (if created), the remote/branch and upload outcome or reason for skipping, followed by a short copyable continuation prompt: read applicable `AGENTS.md`, read the current snapshot in `progress/progress.md`, verify relevant workspace state, then continue the next action; open a linked handoff only if details are missing. Do not paste the entire handoff into the reply or start a new conversation automatically.
