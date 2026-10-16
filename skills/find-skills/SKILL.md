---
name: find-skills
description: Helps users discover and install agent skills when they ask questions like "how do I do X", "find a skill for X", "is there a skill that can...", or express interest in extending capabilities. This skill should be used when the user is looking for functionality that might exist as an installable skill.
---

# Find Skills

This skill helps you discover and install skills from the open agent skills ecosystem.

## When to Use This Skill

Use this skill when the user:

- Asks "how do I do X" where X might be a common task with an existing skill
- Says "find a skill for X" or "is there a skill for X"
- Asks "can you do X" where X is a specialized capability
- Expresses interest in extending agent capabilities
- Wants to search for tools, templates, or workflows
- Mentions they wish they had help with a specific domain (design, testing, deployment, etc.)

## What is the Skills CLI?

The Skills CLI (`npx skills`) is the package manager for the open agent skills ecosystem. Skills are modular packages that extend agent capabilities with specialized knowledge, workflows, and tools.

**Key commands:**

- `npx skills find [query] [--owner <owner>]` - Search for skills interactively or by keyword, optionally scoped to a GitHub owner
- `npx skills add <package>` - Install a skill from GitHub or other sources
- `npx skills update` - Update all installed skills

**Browse skills at:** https://skills.sh/

## How to Help Users Find Skills

### Step 1: Understand What They Need

When a user asks for help with something, identify:

1. The domain (e.g., React, testing, design, deployment)
2. The specific task (e.g., writing tests, creating animations, reviewing PRs)
3. Whether this is a common enough task that a skill likely exists

### Step 2: Check the Leaderboard First

Before running a CLI search, check the [skills.sh leaderboard](https://skills.sh/) to see if a well-known skill already exists for the domain. The leaderboard ranks skills by total installs, surfacing the most popular and battle-tested options.

For example, top skills for web development include:
- `vercel-labs/agent-skills` — React, Next.js, web design (100K+ installs each)
- `anthropics/skills` — Frontend design, document processing (100K+ installs)

### Step 3: Search for Skills

If the leaderboard doesn't cover the user's need, run the find command:

```bash
npx skills find [query] [--owner <owner>]
```

For example:

- User asks "how do I make my React app faster?" → `npx skills find react performance`
- User asks "can you help me with PR reviews?" → `npx skills find pr review`
- User asks "I need to create a changelog" → `npx skills find changelog`

### Step 4: Verify Quality Before Recommending

**Do not recommend a skill based solely on search results.** Always verify:

1. **Install count** — Prefer skills with 1K+ installs. Be cautious with anything under 100.
2. **Source reputation** — Official sources (`vercel-labs`, `anthropics`, `microsoft`) are more trustworthy than unknown authors.
3. **GitHub stars** — Check the source repository. A skill from a repo with <100 stars should be treated with skepticism.

### Step 5: Present Options to the User

When you find relevant skills, present them to the user with:

1. The skill name and what it does
2. The install count and source
3. The install command they can run
4. A link to learn more at skills.sh

Example response:

```
I found a skill that might help! The "react-best-practices" skill provides
React and Next.js performance optimization guidelines from Vercel Engineering.
(185K installs)

To install it:
npx skills add vercel-labs/agent-skills@react-best-practices

Learn more: https://skills.sh/vercel-labs/agent-skills/react-best-practices
```

### Step 6: Offer to Install

If the user wants to proceed, you can install the skill for them:

```bash
npx skills add <owner/repo@skill> -g -y
```

The `-g` flag installs globally (user-level) and `-y` skips confirmation prompts.

## Common Skill Categories

When searching, consider these common categories:

| Category        | Example Queries                          |
| --------------- | ---------------------------------------- |
| Web Development | react, nextjs, typescript, css, tailwind |
| Testing         | testing, jest, playwright, e2e           |
| DevOps          | deploy, docker, kubernetes, ci-cd        |
| Documentation   | docs, readme, changelog, api-docs        |
| Code Quality    | review, lint, refactor, best-practices   |
| Design          | ui, ux, design-system, accessibility     |
| Productivity    | workflow, automation, git                |

## Tips for Effective Searches

1. **Use specific keywords**: "react testing" is better than just "testing"
2. **Try alternative terms**: If "deploy" doesn't work, try "deployment" or "ci-cd"
3. **Check popular sources**: Many skills come from `vercel-labs/agent-skills` or `ComposioHQ/awesome-claude-skills`

## When No Skills Are Found

If no relevant skills exist:

1. Acknowledge that no existing skill was found
2. Offer to help with the task directly using your general capabilities
3. Suggest the user could create their own skill with `npx skills init`

Example:

```
I searched for skills related to "xyz" but didn't find any matches.
I can still help you with this task directly! Would you like me to proceed?

If this is something you do often, you could create your own skill:
npx skills init my-xyz-skill
```

---

## 本环境适配（agent-workspace 维护）

上游来源：https://github.com/vercel-labs/skills （MIT License，v1.7.2 入库）。本节是 agent-workspace 的本地约定，其余章节保持上游原样。

- **CLI 已全局安装**：`npm install -g skills`，命令名 `skills`；未安装的机器可退回 `npx skills`。
- **装到哪（本环境关键）**：DSH 会话与 agentctl 都从 `~/.agents/skills/` 读技能。全局安装必须显式指定一个全局目录恰为 `~/.agents/skills` 的 agent（推荐 `pi`）：

  ```bash
  skills add <owner/repo@skill> -g -a pi -y
  ```

  不带 `-a` 时 CLI 自动探测机器上的 agent 并强制附加全部 universal agent：技能仍会落到 `~/.agents/skills/`，但会同时尝试写入其它 agent 目录（如 `~/.codex/skills/`），输出噪杂且可能报错。新装技能要等 DSH 刷新技能目录后才可见（通常是下一个回合）。
- **项目级安装**：在项目根目录执行 `skills add <owner/repo> -a universal -y`，写入 `<项目>/.agents/skills/` 并生成 `skills-lock.json`（可提交，团队共享）。
- **删除**：用 `skills remove <name> -y`，**不要带 `-a`**——只指定单个 agent 时，若 CLI 探测到其它 agent 共用同一份 canonical 拷贝，会故意保留文件（防误删共享技能）。
- **与 agentctl 共存**：`~/.agents/skills/` 里 agentctl 管理的技能是 junction（指向本仓库 `skills/`），skills CLI 安装的是真实目录，两者可共存。同名冲突时以本仓库为准：`agentctl link` 会先把外来目录备份到 `backups/` 再重建 junction。
- **内网机**：`add` / `find` / `update` 需要公网；`list` / `remove` 可离线使用。
- **遥测**：CLI 会向 skills.sh 发送安装/搜索事件参数（版本、来源、技能名，不含机器标识）。设置环境变量 `DISABLE_TELEMETRY=1` 可关闭。
