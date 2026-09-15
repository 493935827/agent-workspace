---
name: code-review
description: Structured code review - correctness, style, and tests.
---

# code-review

Example skill shipped with the agent-workspace MVP.

## When to use

- Reviewing a diff or pull request
- Deciding what belongs in a review comment vs. a ticket

## Checklist

1. Correctness: does the change do what it claims?
2. Edge cases: empty inputs, errors, concurrency
3. Tests: is the new behavior covered?
4. Style: does it match the surrounding code?

## Notes

- Placeholder content: replace with your real skill.
- Enabled for every environment via `configs/common.yaml`.