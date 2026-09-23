# GitHub ticket tracker

Use this path only when `/run-tickets` receives a GitHub parent issue. The parent is the batch map; its linked child issues are the ticket set. Do not broaden the run to every open issue in the repository.

## Read the live graph

1. Resolve the repository and parent from `#123`, `owner/repo#123`, or a GitHub issue URL. Reject pull-request URLs: this input must identify an issue.
2. Read `docs/agents/issue-tracker.md` and the parent issue. Use the GitHub app for normal issue reads; use `gh`/GitHub API only when it is needed to read linked child issues or native dependency links.
3. For every child, load title, body, comments, labels, assignee, state, and dependency data. Prefer native GitHub issue dependencies. If unavailable, parse a top-level `Blocked by: #12, #34` line in the issue body.
4. Validate the graph before changing code: every blocker must be a ticket child, no issue may block itself, and every dependency cycle must be reported as an issue-number path.

GitHub's native `issue_dependencies_summary.blocked_by` contains only open blockers. It is a live gate, but it is not enough by itself: a blocker also needs the runner's verified integration evidence before it unlocks dependents.

## State mapping and writes

Read project-specific label meanings from `docs/agents/triage-labels.md` when present. Otherwise use the available labels conservatively:

| Runner meaning | GitHub representation |
| --- | --- |
| ready | open issue with `ready-for-agent`, no assignee, no open blocker |
| in progress | open issue with project in-progress/claimed label or assignment |
| done | closed issue, integration commit + passed verification comment |
| failed | open issue with `failed` label or a failure comment |
| needs info | open issue with `needs-info` label and a single decision question |
| integration conflict | open issue with `integration-conflict` label/comment |

Never invent labels when the repository has a documented vocabulary. If there is no safe label or assignment convention, use one concise, idempotent comment that includes `run-tickets`, the ticket issue number, worker branch, commit when available, and verification result. Before adding a comment, search the issue for an existing matching marker to prevent duplicates during restart.

Close a ticket only after its commit is on the integration branch and required integration verification passes. For a failed, needs-info, or semantic-conflict ticket, leave the issue open with its recovery location and compact reason. Re-read all live GitHub state at every new wave and after every restart.
