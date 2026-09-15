---
name: internal-doc-search
description: Intranet-only internal documentation search helper.
---

# internal-doc-search

Example skill for the `intranet` environment.

## When to use

- Searching internal wikis and doc servers (no public internet)
- Pointing at `INTERNAL_DOC_URL` from `.env`

## Notes

- Enabled via `configs/intranet.yaml`.
- This machine never runs `agentctl update` against a network remote;
  it is updated with offline bundles (`agentctl import`).