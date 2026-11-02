---
name: internal-doc-search
description: Intranet-only internal documentation search helper - query the internal doc server and cite results with source paths. Skeleton template for the intranet environment; fill in company specifics before real use.
---

# internal-doc-search

Intranet-environment skill for searching internal documentation. **Skeleton template**: the search entry point, credential handling, index scope, and citation convention are company facts marked `TODO(公司环境)` — fill them in before real use.

## When to use

- Finding how an internal module, protocol, or process is documented (wikis, doc servers, design archive).
- Checking whether an internal convention already exists before inventing one.
- Any lookup where public internet search is unavailable or inappropriate — on the intranet machine (`configs/intranet.yaml`) public internet is off (`network.internet: false`).

## Prerequisites

- Intranet environment with `INTERNAL_DOC_URL` set in `.env` (optional secret, see `.env.example`).
- If `INTERNAL_DOC_URL` is unset, stop and ask the user for the doc server address. Do not fall back to public internet search on an intranet machine.
- `<!-- TODO(公司环境): 检索入口形式（REST API / 内部 Web UI / 共享目录路径，给出可复制的入口） -->`
- `<!-- TODO(公司环境): 访问凭证与方式（只读账号？单点登录？是否需要内网 VPN） -->`
- `<!-- TODO(公司环境): 索引覆盖范围（哪些站点/目录已收录、更新频率） -->`

## Query workflow

1. **Clarify the target** — turn the question into 2–3 candidate keywords, including both language variants and internal codenames.
   - `<!-- TODO(公司环境): 内部常用代号/缩写表（芯片、模块、项目代号），检索时优先带上 -->`
2. **Search** through the entry filled in above:
   - `<!-- TODO(公司环境): 具体检索命令或请求示例（curl/内部工具名 + URL 模板，写成一个可直接跑的片段） -->`
   - Rank hits by: exact codename match > recently modified > authoritative source (design docs beat chat exports).
3. **Verify before trusting** — check the document's date and owning team. A hit about a retired module is worse than no hit; prefer the newest revision of the same doc.
4. **Cite** — every claim taken from a document carries its source in the format below. If a fact cannot be cited (only hearsay), label it explicitly as unverified.

Offline updates only: this machine never runs `agentctl update` against a network remote; new doc bundles arrive via `agentctl import`.

## Result citation format

Cite so a colleague can reopen the exact source without asking you:

```text
<conclusion> — source: <doc title>, <owning team/author>, <last-updated date>
  <INTERNAL_DOC_URL path or share path + section/line>
```

Example shape (URL is a placeholder, not a real address):

```text
I2C bus uses a 10 ms timeout per transfer — source: 《I2C Driver Design》, MCU 团队, 2026-03
  <TODO(公司环境): e.g. http://doc.internal/drivers/i2c-design#timeout>
```

## Notes

- Enabled via `configs/intranet.yaml`.
- Search stays inside the intranet; never relay internal document content to external services.
