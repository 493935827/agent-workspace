---
name: document-helper
description: Company document drafting and formatting helpers - design docs, RFCs, meeting notes - draft, apply company formatting conventions, and route for review. Skeleton template for the company environment; fill in company specifics before real use.
---

# document-helper

Company-environment skill for drafting and formatting internal documents. **This file is a skeleton template**: every company-specific fact is marked `TODO(公司环境)` and must be filled in on the company machine before the skill is used for real work.

## When to use

- Drafting design docs, RFCs, test reports, or meeting notes for internal circulation.
- Reformatting an existing document to company conventions before submission.
- Preparing a document to enter the approval/review workflow.

## Prerequisites

- Working on the company environment (enabled via `configs/company.yaml`).
- `<!-- TODO(公司环境): 公司文档模板库路径（如共享盘/Intranet 下载页的具体位置） -->`
- `<!-- TODO(公司环境): 文档格式规范文档的位置与版本（如《技术文档编写规范 vX.Y》，格式冲突时以它为准） -->`
- `<!-- TODO(公司环境): 各文档类型的审批人/评审流程入口（如 OA 系统链接、评审群） -->`

## Workflow

1. **Draft** — pick the template for the document type, then fill content before touching any formatting:
   - `<!-- TODO(公司环境): 设计文档模板路径 -->`
   - `<!-- TODO(公司环境): 会议纪要模板路径 -->`
   - `<!-- TODO(公司环境): 测试报告模板路径 -->`

   Minimum content skeleton: 背景 → 方案/结论 → 风险与影响 → 遗留问题（每项有 owner 和日期）.
2. **Format** — apply company conventions to the drafted content:
   - `<!-- TODO(公司环境): 页眉页脚/文档编号/字体字号/密级标注等格式要求（引用规范文档的具体条目） -->`
3. **Review** — self-check, then route for approval:
   - Self-check: cited numbers have sources, action items have owners and dates, classification marking matches the content.
   - `<!-- TODO(公司环境): 提审方式与审批链（哪类文档找谁审） -->`

## Output requirements

- Deliver in the format and naming the reviewer expects:
  - `<!-- TODO(公司环境): 交付格式（.docx/.pdf 等）与命名规则（如 YYYYMMDD-<类型>-<标题>.docx） -->`
- One document per file; keep the filled template's structure intact so reviewers can compare against the standard.
- Company-confidential content stays on company machines and inside company tools — never paste it into external services.

## Notes

- Enabled via `configs/company.yaml`.
- Keep company content on company machines only.
