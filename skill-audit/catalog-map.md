# 会话可见技能与三处本地目录装载差异比对（catalog-map）

- 审计时间：2026-11-02 17:33
- 任务：t4（团队成员 catalog-mapper，只读比对）
- 方法：以本会话运行时 `available_skills` 名单（38 个）为基准，逐一对照三处本地技能目录的顶层条目（`Get-ChildItem -Force`，含隐藏条目）。
- 只读声明：本次比对未修改任何技能内容，未触碰任何 `dist\` 目录；本报告是本轮唯一写入的文件。

## 0. 三处本地目录实际清单（快速统计）

| 位置 | 顶层条目 | 说明 |
| --- | --- | --- |
| `D:\App\agent-workspace\skills` | 48 个技能目录 + 1 个散置文件 `serial-debug.7z` | 散置压缩包仅记录，不计为技能目录 |
| `C:\Users\E0465\.agents\skills` | 48 个技能目录 | 无散置文件 |
| `C:\Users\E0465\.codex\skills` | `.system`、`hatch-pet` 两个目录 | `.system` 内含 6 个技能目录（imagegen、openai-docs、plugin-creator、review-agent、skill-creator、skill-installer）和 1 个标记文件 `.codex-system-skills.marker` |

## 1. 会话可见且本地存在的技能表（38/38 全部命中本地）

标记说明：✓ = 存在该目录；"仅 .system" = 仅存在于 `C:\Users\E0465\.codex\skills\.system\` 下。

| # | 技能名 | workspace skills/ | ~\.agents\skills | ~\.codex\skills |
| --- | --- | --- | --- | --- |
| 1 | agent-reach | ✓ | ✓ | — |
| 2 | andes-aice-bringup | ✓ | ✓ | — |
| 3 | cli-anything | — | ✓ | — |
| 4 | cli-hub-meta-skill | — | ✓ | — |
| 5 | code-review | ✓ | ✓ | — |
| 6 | codebase-design | ✓ | ✓ | — |
| 7 | define-bounded-goal | ✓ | ✓ | — |
| 8 | diagnosing-bugs | ✓ | ✓ | — |
| 9 | document-helper | ✓ | ✓ | — |
| 10 | domain-modeling | ✓ | ✓ | — |
| 11 | find-skills | ✓ | ✓ | — |
| 12 | git-delivery | ✓ | ✓ | — |
| 13 | git-helper | ✓ | ✓ | — |
| 14 | grilling | ✓ | ✓ | — |
| 15 | hallmark | — | ✓ | — |
| 16 | imagegen | — | — | 仅 .system |
| 17 | jira-helper | ✓ | ✓ | — |
| 18 | onenote | ✓ | ✓ | — |
| 19 | openai-docs | — | — | 仅 .system |
| 20 | pack-to-dts | ✓ | ✓ | — |
| 21 | plugin-creator | — | — | 仅 .system |
| 22 | project-structure | ✓ | ✓ | — |
| 23 | prototype | ✓ | ✓ | — |
| 24 | pyside6-fluent-ui | ✓ | ✓ | — |
| 25 | python-helper | ✓ | ✓ | — |
| 26 | qt-ui-design | ✓ | ✓ | — |
| 27 | reg-to-ll | ✓ | ✓ | — |
| 28 | research | ✓ | ✓ | — |
| 29 | resolving-merge-conflicts | ✓ | ✓ | — |
| 30 | reverse-engineer-anything | ✓ | ✓ | — |
| 31 | review-agent | — | — | 仅 .system |
| 32 | serial-debug | ✓ | ✓ | — |
| 33 | skill-creator | — | — | 仅 .system |
| 34 | skill-installer | — | — | 仅 .system |
| 35 | tdd | ✓ | ✓ | — |
| 36 | ui-ux-pro-max | ✓ | ✓ | — |
| 37 | wizard | ✓ | ✓ | — |
| 38 | writing-for-agents | ✓ | ✓ | — |

分布汇总：workspace+agents 双处 29 个；仅 agents 3 个（cli-anything、cli-hub-meta-skill、hallmark）；仅 codex .system 6 个（imagegen、openai-docs、plugin-creator、review-agent、skill-creator、skill-installer）；仅 workspace 0 个；三处齐备 0 个。

## 2. 会话可见但三处本地目录都没有的技能

- 无（0 个）。会话可见的 38 个技能全部能在三处本地目录之一找到。
- 标注：其中 6 个（imagegen、openai-docs、plugin-creator、review-agent、skill-creator、skill-installer）位于 `C:\Users\E0465\.codex\skills\.system\`，该目录带有 `.codex-system-skills.marker` 标记文件，特征上像随 Codex 程序内置的"系统技能"而非用户安装技能；按任务要求仅作标注，不下结论。

## 3. 磁盘上存在但本会话不可见的技能（分位置）

### `D:\App\agent-workspace\skills`（19 个）

ask-matt、firmware-mentor、game-dev、grill-me、grill-with-docs、handoff、image-tools、implement、improve-codebase-architecture、internal-doc-search、run-tickets、setup-matt-pocock-skills、teach、to-questionnaire、to-spec、to-tickets、triage、wait-what、wayfinder

- 其中 `firmware-mentor` 在会话规则中约定"仅在用户当前消息明确写出 `$firmware-mentor` 时加载"，本次会话未触发，故未见于可见名单（仅事实记录）。
- 事实并列：会话可见的 `imagegen`（来自 codex .system）与仅 workspace 存在的 `image-tools` 是两个不同名字的目录。

### `C:\Users\E0465\.agents\skills`（16 个）

ask-matt、firmware-mentor、grill-me、grill-with-docs、handoff、implement、improve-codebase-architecture、run-tickets、setup-matt-pocock-skills、teach、to-questionnaire、to-spec、to-tickets、triage、wait-what、wayfinder

- 这 16 个与 workspace 侧 19 个的差集仅为 workspace 独有的 game-dev、image-tools、internal-doc-search，其余完全同名。

### `C:\Users\E0465\.codex\skills`（1 个）

- hatch-pet（用户层；`.system` 内的 6 个技能全部会话可见，无遗漏）

### 三处目录两两存在性差异（补充）

- 仅 workspace 有：game-dev、image-tools、internal-doc-search（3 个）
- 仅 ~\.agents\skills 有：cli-anything、cli-hub-meta-skill、hallmark（3 个）
- 仅 ~\.codex\skills 有：hatch-pet（用户层）及 .system 的 6 个系统技能
- workspace 另有散置文件 `serial-debug.7z`，与同名技能目录并存（仅记录）

## 4. 简短结论（本地技能装载覆盖情况的初步判断）

本会话可见的 38 个技能与本地磁盘完全对得上，没有"凭空出现"的会话技能：29 个同时存在于 workspace `skills/` 与 `~\.agents\skills`（workspace 侧可见集合是 agents 侧可见集合的子集），3 个仅由 `~\.agents\skills` 独有提供（cli-anything、cli-hub-meta-skill、hallmark），6 个由 `~\.codex\skills\.system` 提供（带系统技能标记文件）。反向看，磁盘上有 20 个不同名字的技能本会话未列出（workspace 19、agents 16、codex 用户层 1），说明三处目录并未被会话全量装载，当前会话的技能可见面主要来自 workspace 与 `~\.agents\skills` 的重叠部分，外加 codex 端 `.system` 的 6 个内置技能。以上为基于目录存在性的初步判断；各技能能否被正确装载还取决于其结构与 frontmatter 完整性，由其他审计项覆盖。
