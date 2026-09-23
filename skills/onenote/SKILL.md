---
name: onenote
description: Operate Microsoft OneNote through the `mcp__onenote` MCP tools. Use when the user asks Codex to search OneNote notes, list notebooks/sections/section groups, read page content, create notebooks/sections/pages, append or replace OneNote page content, attach local files or images to pages, or delete OneNote pages.
---

# OneNote

## Overview

Use the `mcp__onenote` tools as the OneNote channel. Treat OneNote as a live external workspace: inspect before editing, preserve existing content unless the user explicitly asks to replace it, and confirm destructive actions.

## Tool Map

- Discover notebooks: `mcp__onenote.list_notebooks`
- Discover sections: `mcp__onenote.list_sections`, optionally scoped by `notebookId`
- Discover section groups: `mcp__onenote.list_section_groups`, optionally scoped by `notebookId`
- Create containers: `mcp__onenote.create_notebook`, `mcp__onenote.create_section`, `mcp__onenote.create_section_group`
- Search pages: `mcp__onenote.search_pages`
- Read pages: `mcp__onenote.read_page`
- Create pages: `mcp__onenote.create_page`
- Edit pages: `mcp__onenote.update_page`
- Delete pages: `mcp__onenote.delete_page`

## Workflow

1. Identify the target notebook, section, or page.
   - If the user names a notebook or section, list notebooks/sections first and choose the closest exact match.
   - If the user names page text or a title, use `search_pages` first.
   - If there are multiple plausible matches, ask the user to choose before writing.

2. Read before changing existing pages.
   - Use `read_page` with `format: "markdown"` for normal reasoning and summaries.
   - Use `read_page` with `format: "html"` when targeting a specific element by `data-id` for `update_page`.

3. Create or update content.
   - For new pages, call `create_page` with `sectionId`, `title`, `content`, and `format`.
   - Prefer Markdown content unless HTML is needed for precise layout.
   - For existing pages, prefer `append` or `prepend` operations over `replace`.
   - Use `replace` only for a clearly bounded target or when the user explicitly asks to rewrite the page.

4. Verify important changes.
   - After creating or updating a page, read it back when the result will be used as a source of truth, the edit was complex, or the user asked for confirmation.
   - Report the notebook/section/page title and a short summary of what changed.

## Creating Pages

Use Markdown by default:

```json
{
  "sectionId": "<section-id>",
  "title": "Bring-up Notes",
  "content": "## Summary\n\n- Item one\n- Item two",
  "format": "markdown"
}
```

For attachments, reference each attachment from content with `name:<name>` and pass either `path` or base64 `data`:

```json
{
  "sectionId": "<section-id>",
  "title": "Debug Capture",
  "content": "![scope capture](name:capture.png)",
  "format": "markdown",
  "attachments": [
    {
      "name": "capture.png",
      "path": "work/capture.png",
      "contentType": "image/png"
    }
  ]
}
```

## Updating Pages

Use `update_page.operations` as an ordered batch. Common operations:

```json
{
  "pageId": "<page-id>",
  "operations": [
    {
      "action": "append",
      "target": "body",
      "content": "## Follow-up\n\n- New note",
      "format": "markdown"
    }
  ]
}
```

For precise edits, read the page as HTML and target `title`, `body`, or a raw `data-id` from the returned HTML. A leading `#` is accepted if copied from a selector.

## Safety Rules

- Always ask for confirmation before calling `delete_page`; deletion is permanent.
- Ask for clarification before creating a new notebook or section when the name may collide with an existing one.
- Do not expose full private page contents unless the user asked to read or summarize them.
- Keep final answers concise: say what was searched, read, created, or changed, and include the exact OneNote titles involved.
- If the OneNote MCP tools are unavailable, say the OneNote channel is not connected and ask the user to enable/install the OneNote MCP integration.

## Troubleshooting

- If a tool returns `Not signed in. Run \`onenote-mcp login\``, the MCP channel is configured but Microsoft auth is missing. Ask the user to run:

```powershell
$env:ONENOTE_MCP_CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
$env:ONENOTE_MCP_TENANT_ID = "common"
onenote-mcp login
```

- If a page cannot be found by title, search for distinctive body text.
- If an edit target is ambiguous, use `read_page(format: "html")` and target the specific `data-id`.
- If a Markdown conversion loses layout, retry with `format: "html"` and a small, valid HTML fragment.
