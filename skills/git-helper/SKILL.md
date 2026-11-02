---
name: git-helper
description: Everyday git recipes - branch hygiene, Conventional Commits messages, layered safe undo (worktree, staged, committed) and accident recovery via reflog. Use when writing or rewording commit messages, creating/cleaning branches, rebasing, undoing changes, or recovering from a git mistake.
---

# git-helper

Recipes for everyday git operations. For anything destructive (`reset --hard`, `push --delete`, history rewrite), state what the command will do before running it.

## When to use

- Creating, naming, or cleaning up branches; deciding merge vs. rebase.
- Writing or rewording commit messages.
- Undoing changes at any layer (worktree, index, commits) or recovering from a botched operation.

## Branch hygiene

- **Naming**: `<type>/<topic>` — `feat/i2c-retry`, `fix/uart-framing`, `chore/deps-bump`. Lowercase, hyphen-separated; no bare personal names (`li/work` tells nobody anything).
- **One topic per branch.** Branch off the branch you depend on, not always main.
- **Create**: prefer `git switch -c <name>` over the older `git checkout -b`.
- **Rebase timing**: rebase private/unpushed branches freely (`git pull --rebase`, `git rebase main`). Never rewrite commits others may have pulled — shared branches take merges instead.
- **Cleanup**:

  ```bash
  git branch --merged main              # list what is safe to delete
  git branch -d fix/uart-framing        # delete (refuses if unmerged)
  git push origin --delete fix/uart-framing
  git fetch --prune                     # drop stale remote-tracking refs
  ```

  Delete right after merge. Use `-D` (force) only when you can say exactly why the work is abandoned.

## Commit messages — Conventional Commits

Format: `<type>(<optional scope>): <summary in imperative mood>`, blank line, then a body wrapped at ~72 chars that explains *why*.

| Type | Use for |
|---|---|
| feat | new user-visible capability |
| fix | bug fix |
| refactor | no behavior change |
| perf | performance-only change |
| test | tests only |
| docs | documentation only |
| build / chore | tooling, deps, scripts |
| revert | `revert: revert "<subject>"` of a bad commit |

Examples: `fix(i2c): bound retry count so bus lockup cannot hang task`, `feat(pyloader): parse extended SREC records`.
The body answers: what breaks without this, and which alternative was rejected. One logical change per commit — a commit whose message needs "and" twice should be two commits.

## Safe undo — three layers

| Goal | Command | Effect |
|---|---|---|
| Discard worktree edits, one file | `git restore <file>` | Uncommitted edits gone (irreversible) |
| Discard all worktree edits | `git restore .` | Same, repo-wide |
| Unstage a file, keep the edits | `git restore --staged <file>` | Edit stays in the worktree |
| Fix last commit (message or missing files) | `git commit --amend` | Replaces HEAD — unpushed commits only |
| Undo last commit, keep changes staged | `git reset --soft HEAD~1` | Worktree untouched |
| Undo last commit, keep changes unstaged | `git reset HEAD~1` | Unstaged |
| Undo last commit, discard everything | `git reset --hard HEAD~1` | Destructive |
| Undo a *pushed* commit on a shared branch | `git revert <sha>` | New commit negating it — history stays intact |
| Move a local branch to another commit | `git branch -f <name> <sha>` | Local branches only |

Rule of thumb: `--soft` when the work is fine but the split/message is wrong; `--hard` only when you can restate exactly what gets deleted.

**reflog fallback** — commits "lost" to a reset or rebase stay reachable for ~90 days:

```bash
git reflog                       # find the pre-disaster HEAD@{n}
git checkout -b rescue HEAD@{2}  # safer: branch the state first, inspect, then move
git reset --hard HEAD@{2}        # only once you are sure
```

## Accident recovery

| Accident | Fix |
|---|---|
| Committed on the wrong branch | `git switch <right>` + `git cherry-pick <sha>`; remove it from the wrong branch with `git reset --hard HEAD~1` (unpushed only) |
| Committed a secret / large file | Unpushed: `git rm --cached <f>` + `git commit --amend`. Pushed: rotate the credential immediately, then rewrite history — removing the file does not un-leak it |
| Messy worktree, need to switch context | `git stash` (or `git stash -u` to include untracked), `git stash pop` when back |
| Rebase went wrong | `git reflog` → `git reset --hard HEAD@{n}` to the commit before it started |
| Merge/rebase conflict mess | `git merge --abort` / `git rebase --abort`, then start over cleanly |
| Deleted an unmerged branch | Its tip is still in `git reflog`; `git branch <name> <sha>` restores it |
| Stranded in detached HEAD with wanted work | `git switch -c <new-branch>` before checking out anything else |

For conflict mechanics mid-merge/rebase, hand off to the `resolving-merge-conflicts` skill.
