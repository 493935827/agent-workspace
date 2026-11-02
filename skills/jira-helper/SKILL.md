---
name: jira-helper
description: Company Jira workflow helpers - look up tickets, transition status, add comments, and build JQL queries. Skeleton template for the company environment; fill in company specifics before real use.
---

# jira-helper

Company-environment skill for day-to-day Jira operations. **Skeleton template**: instance URL, auth convention, project keys, and status names are company facts marked `TODO(公司环境)` — fill them in before real use. The request shapes below follow Jira REST API v3 and work once the placeholders are filled.

## When to use

- Looking up a ticket's state, comments, or linked work.
- Transitioning a ticket (start progress, submit for review, close).
- Adding a formatted comment or a sprint summary.
- Building a JQL query for a team board or status report.

## Prerequisites

- Company environment (enabled via `configs/company.yaml`) with the `COMPANY_TOKEN` secret set in `.env` (see `.env.example`; `agentctl doctor` reports set/missing without values).
- `<!-- TODO(公司环境): Jira 实例 base URL（如 https://jira.<company-domain>） -->`
- `<!-- TODO(公司环境): COMPANY_TOKEN 的使用方式（Bearer header / Basic + 用户名字段） -->`
- `<!-- TODO(公司环境): 本团队常用 project key 列表 -->`

## Common operations

Examples use `curl` against REST API v3; replace `$BASE` with the filled-in base URL.

Look up a ticket:

```bash
curl -s -H "Authorization: Bearer $COMPANY_TOKEN" "$BASE/rest/api/3/issue/PROJ-123"
```

Transition a ticket — always list valid transitions first, then apply the returned ID (never guess IDs):

```bash
curl -s -H "Authorization: Bearer $COMPANY_TOKEN" "$BASE/rest/api/3/issue/PROJ-123/transitions"
curl -s -X POST -H "Authorization: Bearer $COMPANY_TOKEN" -H "Content-Type: application/json" \
  -d '{"transition": {"id": "<id from the previous step>"}}' \
  "$BASE/rest/api/3/issue/PROJ-123/transitions"
```

Add a comment (API v3 uses the Atlassian Document Format):

```bash
curl -s -X POST -H "Authorization: Bearer $COMPANY_TOKEN" -H "Content-Type: application/json" \
  -d '{"body": {"type": "doc", "version": 1, "content": [{"type": "paragraph",
        "content": [{"type": "text", "text": "<comment text>"}]}]}}' \
  "$BASE/rest/api/3/issue/PROJ-123/comment"
```

Rules of engagement:

- `<!-- TODO(公司环境): 状态流转约定（哪些状态允许跳转、谁有权流转、流转是否需要先填字段） -->`
- Write ticket comments so a reader two weeks later understands the *decision*, not just the action; include the ticket key in any commit that references it.

## JQL starter templates

Replace `PROJ`, `ME`, and the status names with the team's real values —
`<!-- TODO(公司环境): 实际使用的状态名称（实例可能是中文，先在 UI 里确认） -->`:

```text
# My open work, priority order
assignee = currentUser() AND project = PROJ AND status != Done ORDER BY priority DESC

# What moved this week (sprint summary input)
project = PROJ AND updated >= -7d ORDER BY updated DESC

# Blocked / waiting items
project = PROJ AND status in ("<TODO: status A>", "<TODO: status B>")

# Open bugs past a two-week target
project = PROJ AND type = Bug AND status != Done AND created <= -14d
```

## Notes

- Enabled via `configs/company.yaml`; requires `COMPANY_TOKEN`.
- Never echo token values into logs, ticket text, or command output.
- Jira content stays inside the company network — do not paste ticket content to external services.
