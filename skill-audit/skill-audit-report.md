# 本地 Skill 审计最终报告（skill-audit / t3）

- 汇总来源：t1 `ws-inventory.md`（工作区结构）、t2 `home-inventory.md`（用户目录）、t4 `catalog-map.md`（会话比对）、t5 `cat-embedded.md`（嵌入式/硬件/逆向 6 个）、t6 `cat-devflow.md`（开发流程 15 个）、t7 `cat-designdoc.md`（设计/UI/文档 10 个）、t8 `cat-meta-misc.md`（元技能/杂项 17 个）。
- 审计方式：只读汇总 + 少量只读复核（dist 快照目录名集合级对比、45 个双处同名技能的 SKILL.md SHA-256 比对、1 处哈希不一致的逐行核实）。
- 约束遵守：本轮唯一写入文件为本文件；未修改任何技能内容，未改动其他审计产出，未触碰 `dist\` 目录内容。

## ① 概览

| 位置 | 顶层技能目录 | 其它构成 |
|---|---|---|
| 工作区 `D:\App\agent-workspace\skills\` | **48** | 另有 1 处嵌套技能 `reg-to-ll\workflow-run-skill`（全树共 49 个 SKILL.md）；根目录有散置非技能文件 `serial-debug.7z`（约 166 MB） |
| `C:\Users\E0465\.agents\skills\` | **48** | 同样含嵌套 `reg-to-ll\workflow-run-skill`；根目录无散置文件；36/48 带 `agents/openai.yaml` |
| `C:\Users\E0465\.codex\skills\` | **1**（`hatch-pet`，用户自装） | `.system` 为 Codex 内置系统技能目录，内含 **6 个全部有效**的内置技能（imagegen、openai-docs、plugin-creator、review-agent、skill-creator、skill-installer）+ 1 个系统标记文件（ID `eb8751f4456f448a`） |

合计 **58 个不同名字的顶层技能目录**：双处共有 45 + 仅工作区 3 + 仅 .agents 3 + 仅 .codex 7。

**会话覆盖**：当前会话可见 38 个技能，**38/38 全部命中本地，0 个"凭空出现"**——29 个在 workspace 与 .agents 双处、3 个仅由 .agents 提供（cli-anything、cli-hub-meta-skill、hallmark）、6 个来自 `.codex\.system`。反向看，磁盘上有 20 个不同名字的技能本会话不可见（workspace 19、agents 16、codex 用户层 1）。

**结构结论**：58 个顶层技能目录 100% 存在 SKILL.md、frontmatter name/description 齐全、正文非空；name 与目录名一致率 57/58，唯一不一致项是嵌套技能 `workflow-run-skill`（name: `workflow-run`），全域无缺失 SKILL.md 的目录。深读覆盖工作区全部 48 个技能（t5+t6+t7+t8 = 6+15+10+17），结论：**可用 36 / 基本可用有小问题 9 / 不可用 3**（空壳示例）。

**总体结论**：三处技能库的结构完整性与会话装载一致性都很高——没有缺失 SKILL.md、没有顶层 name 错位、没有会话技能找不到本地来源，且 `disable-model-invocation` 隐藏机制双向零错位。主要风险不在结构而在内容与依赖：3 个空壳示例与 3 个占位正文技能名实不符；reg-to-ll 飞书链路（缺 feishu-fetch）、agent-reach（缺后端 CLI）、onenote（缺 MCP）三处存在缺失依赖；serial-debug 目录混入约 6720 个 .venv/构建产物文件、skills/ 根散置 166 MB 压缩包。另有 8 个工程流程技能依赖一次性 `/setup-matt-pocock-skills` 配置，本工作区从未运行（多数有兜底，run-tickets 无）。

## ② 存在性矩阵

58 个顶层技能目录 × 三处位置。✓ = 存在；— = 不存在；★ = 仅该处存在。**会话可见** = 当前会话技能目录在列；**深读结论** = 工作区副本的分类深读结果（"未深读"= 仅 t2 结构审计覆盖）。

| # | 技能目录 | workspace skills/ | ~\.agents\skills | ~\.codex\skills | 会话可见 | 深读结论 |
|---|---|---|---|---|---|---|
| 1 | agent-reach | ✓ | ✓ | — | 可见 | 基本可用（缺后端 CLI，环境依赖） |
| 2 | andes-aice-bringup | ✓ | ✓ | — | 可见 | 可用 |
| 3 | ask-matt | ✓ | ✓ | — | 不可见 | 可用 |
| 4 | cli-anything | — | ✓★ | — | 可见 | 未深读 |
| 5 | cli-hub-meta-skill | — | ✓★ | — | 可见 | 未深读 |
| 6 | codebase-design | ✓ | ✓ | — | 可见 | 可用 |
| 7 | code-review | ✓ | ✓ | — | 可见 | 基本可用（占位骨架） |
| 8 | define-bounded-goal | ✓ | ✓ | — | 可见 | 基本可用（token_budget 参数漂移） |
| 9 | diagnosing-bugs | ✓ | ✓ | — | 可见 | 可用 |
| 10 | document-helper | ✓ | ✓ | — | 可见 | **不可用（空壳示例）** |
| 11 | domain-modeling | ✓ | ✓ | — | 可见 | 可用 |
| 12 | find-skills | ✓ | ✓ | — | 可见 | 可用 |
| 13 | firmware-mentor | ✓ | ✓ | — | 不可见 | 可用（$ 显式调用设计） |
| 14 | game-dev | ✓★ | — | — | 不可见 | 可用（示例技能） |
| 15 | git-delivery | ✓ | ✓ | — | 可见 | 可用 |
| 16 | git-helper | ✓ | ✓ | — | 可见 | 基本可用（占位骨架） |
| 17 | grill-me | ✓ | ✓ | — | 不可见 | 可用（薄包装） |
| 18 | grill-with-docs | ✓ | ✓ | — | 不可见 | 可用（薄包装） |
| 19 | grilling | ✓ | ✓ | — | 可见 | 可用 |
| 20 | hallmark | — | ✓★ | — | 可见 | 未深读 |
| 21 | handoff | ✓ | ✓ | — | 不可见 | 可用 |
| 22 | hatch-pet | — | — | ✓★（用户层） | 不可见 | t2：有效技能（37.3KB/539 行 + 9 脚本） |
| 23 | image-tools | ✓★ | — | — | 不可见 | 可用（示例技能） |
| 24 | imagegen | — | — | ✓（.system） | 可见 | t2：内置有效 |
| 25 | implement | ✓ | ✓ | — | 不可见 | 可用 |
| 26 | improve-codebase-architecture | ✓ | ✓ | — | 不可见 | 可用 |
| 27 | internal-doc-search | ✓★ | — | — | 不可见 | **不可用（空壳示例）** |
| 28 | jira-helper | ✓ | ✓ | — | 可见 | **不可用（空壳示例）** |
| 29 | onenote | ✓ | ✓ | — | 可见 | 基本可用（OneNote MCP 未检出，环境依赖） |
| 30 | openai-docs | — | — | ✓（.system） | 可见 | t2：内置有效 |
| 31 | pack-to-dts | ✓ | ✓ | — | 可见 | 可用 |
| 32 | plugin-creator | — | — | ✓（.system） | 可见 | t2：内置有效 |
| 33 | project-structure | ✓ | ✓ | — | 可见 | 可用 |
| 34 | prototype | ✓ | ✓ | — | 可见 | 可用 |
| 35 | pyside6-fluent-ui | ✓ | ✓ | — | 可见 | 可用 |
| 36 | python-helper | ✓ | ✓ | — | 可见 | 基本可用（正文占位，名实不符） |
| 37 | qt-ui-design | ✓ | ✓ | — | 可见 | 可用 |
| 38 | reg-to-ll | ✓ | ✓ | — | 可见 | 基本可用（飞书链路缺 feishu-fetch） |
| 39 | research | ✓ | ✓ | — | 可见 | 可用 |
| 40 | resolving-merge-conflicts | ✓ | ✓ | — | 可见 | 可用 |
| 41 | reverse-engineer-anything | ✓ | ✓ | — | 可见 | 可用（双副本 SKILL.md 漂移，见 C21） |
| 42 | review-agent | — | — | ✓（.system） | 可见 | t2：内置有效 |
| 43 | run-tickets | ✓ | ✓ | — | 不可见 | 基本可用（配置/路径问题） |
| 44 | serial-debug | ✓ | ✓ | — | 可见 | 可用（目录卫生差） |
| 45 | setup-matt-pocock-skills | ✓ | ✓ | — | 不可见 | 可用 |
| 46 | skill-creator | — | — | ✓（.system） | 可见 | t2：内置有效 |
| 47 | skill-installer | — | — | ✓（.system） | 可见 | t2：内置有效 |
| 48 | tdd | ✓ | ✓ | — | 可见 | 可用 |
| 49 | teach | ✓ | ✓ | — | 不可见 | 基本可用（孤儿支撑文件） |
| 50 | to-questionnaire | ✓ | ✓ | — | 不可见 | 可用 |
| 51 | to-spec | ✓ | ✓ | — | 不可见 | 可用（需先 setup） |
| 52 | to-tickets | ✓ | ✓ | — | 不可见 | 可用（需先 setup） |
| 53 | triage | ✓ | ✓ | — | 不可见 | 可用（需先 setup） |
| 54 | ui-ux-pro-max | ✓ | ✓ | — | 可见 | 可用（README 空引用、路径模板） |
| 55 | wait-what | ✓ | ✓ | — | 不可见 | 可用 |
| 56 | wayfinder | ✓ | ✓ | — | 不可见 | 可用 |
| 57 | wizard | ✓ | ✓ | — | 可见 | 可用 |
| 58 | writing-for-agents | ✓ | ✓ | — | 可见 | 可用 |

统计：双处共有 45、仅 workspace 3（game-dev、image-tools、internal-doc-search）、仅 ~\.agents\skills 3（cli-anything、cli-hub-meta-skill、hallmark）、仅 ~\.codex\skills 7（hatch-pet + .system 6 个）。

补充登记：

- **嵌套技能 1 处**（不计入上表）：`reg-to-ll\workflow-run-skill`，workspace 与 .agents 均存在；frontmatter `name: workflow-run` 与目录名不一致，frontmatter 额外含 prerequisites 与 `language: zh-CN`。
- workspace `skills/` 根散置文件 `serial-debug.7z`（约 166 MB），与同名技能目录并存；.agents 与 .codex 根均无散置文件。
- **t3 复核新发现**：45 个双处同名技能的 SKILL.md SHA-256 逐一比对，44 个完全一致，**1 个不同**——`reverse-engineer-anything`：工作区副本 23,865 B（2026-10-23）、.agents 副本 23,523 B（2026-10-21），差异为 .agents 版 frontmatter 多一个 `tool_count: 207` 键（两版 `metadata.version` 均为 "42"）。证明两处副本并非逐字节同步，属登记性漂移（详见 C21）。

## ③ 会话可见性差异

**会话可见但本地没有：0 个。** 38 个会话技能全部命中三处本地目录之一，不存在"内置/插件凭空装载"。其中 6 个（imagegen、openai-docs、plugin-creator、review-agent、skill-creator、skill-installer）位于 `~\.codex\skills\.system\`，该目录带 `.codex-system-skills.marker` 标记文件，特征为随 Codex 程序内置的"系统技能"（非用户安装）。

**磁盘存在但会话不可见：20 个不同名字。**

| 位置 | 数量 | 名单 | 原因归类 |
|---|---|---|---|
| workspace `skills/` | 19 | ask-matt、firmware-mentor、grill-me、grill-with-docs、handoff、implement、improve-codebase-architecture、run-tickets、setup-matt-pocock-skills、teach、to-questionnaire、to-spec、to-tickets、triage、wait-what、wayfinder（16 个，与 .agents 重合）＋ game-dev、image-tools、internal-doc-search（3 个，仅 workspace） | 16 个带 `disable-model-invocation: true`（设计使然的手动调用技能）；game-dev 与 `configs/company.yaml` 的 `exclude_skills` 一致；image-tools 在 company.yaml 未排除但同样不可见，属环境装配行为（仅记录事实）；internal-doc-search 为 intranet 示例技能 |
| ~\.agents\skills | 16 | 同上 16 个 `disable-model-invocation` 技能 | 同上 |
| ~\.codex\skills | 1 | hatch-pet | 会话技能目录未列出该用户层技能；同目录 .system 的 6 个全部可见。原因属宿主装载策略，本轮审计未查明（仅事实记录） |

补充事实：

- **隐藏机制零错位**：16 个不可见技能全部带 `disable-model-invocation: true`，且无"未标记却不可见"或"已标记却可见"的错位（t6/t8 在开发流程类与元技能类双向核对一致）；可见技能的 description 与磁盘 frontmatter 抽验逐字一致（t6 的 8 个可见技能）。
- **磁盘隐藏 ≠ 不可用**：`setup-matt-pocock-skills` 虽不在会话目录中，仍可通过用户显式调用进入对话（本轮即以显式调用形式出现）；`firmware-mentor` 另受工作区 AGENTS.md 约束，仅当用户消息明确写 `$firmware-mentor` 时加载。
- 会话可见集是 .agents 可见集的子集：.agents 独有的 3 个技能全部可见，workspace 独有的 3 个全部不可见。

## ④ 问题清单

分级口径：**不可用** = 作为实际能力不可交付；**阻碍触发或装载** = 会阻碍技能被正确触发、按文档调用或完成其声明链路；**小问题** = 卫生/一致性/文档失实缺陷；**建议项** = 配置、依赖与可选优化。来源标注（t1–t8，"t3 复核"为本轮汇总复核新发现）。

### A. 不可用（3 个）

| 技能 | 问题 | 来源 |
|---|---|---|
| document-helper | 空壳示例：正文 18 行，无任何可执行指令/模板/格式规范/脚本（自述 "Example skill for the `company` environment"）；description 笼统 | t7 |
| internal-doc-search | 空壳示例（intranet 环境）：无检索指令、无工具名、无查询模式；引用的 `configs/intranet.yaml`、`INTERNAL_DOC_URL`、`agentctl update/import` 均真实存在，只缺实质内容 | t7 |
| jira-helper | 空壳示例（company 环境）：无 JQL 示例、无 API/CLI 命令、无工单流转说明；`configs/company.yaml` 与 `COMPANY_TOKEN` 真实存在 | t7 |

### B. 阻碍触发或装载的问题（11 项，中危为主）

| # | 对象 | 问题 | 来源 |
|---|---|---|---|
| B1 | reg-to-ll | 飞书输入链路依赖的 `feishu-fetch` 技能在三处技能目录均不存在——飞书链路本地不可用（本地 Excel `--source local` 链路完整可用） | t5 |
| B2 | ui-ux-pro-max | SKILL.md 写 "see README for install instructions if Python is missing"，但目录内不存在 README.md——空引用，Python 缺失时无指引可看 | t7 |
| B3 | ui-ux-pro-max | 全部调用命令写死 `${CLAUDE_PLUGIN_ROOT}/.claude/skills/ui-ux-pro-max/scripts/search.py` 路径模板，在当前 `skills/` 布局下不成立，需 agent 自行改写 | t7 |
| B4 | run-tickets | 无条件引用 `docs/agents/issue-tracker.md`，本工作区无 `docs/` 目录（setup 从未运行，GitHub 模式配置缺失）；同文件其它同类引用均为条件式可兜底，此处没有 | t6 |
| B5 | run-tickets | helper 调用硬编码 `$env:USERPROFILE\.agents\skills\run-tickets\...` 绝对路径：与工作区副本双份并存（漂移风险），且换安装位置即失效 | t6 |
| B6 | code-review | 正文自声明占位示例（"Example skill…/Placeholder content"），实质仅 4 条通用清单；description 无触发场景；tdd/implement 引用其作收尾环节，引导深度不足 | t6 |
| B7 | git-helper | 占位示例 + 残留测试痕迹标题 "Update note (simulated edit on personal machine)"；description 触发场景弱 | t6 |
| B8 | python-helper | 正文自述 "Placeholder content: replace with your real skill"，无任何实质 snippets，与 description 承诺（idioms/packaging/debugging snippets）名实不符 | t8 |
| B9 | agent-reach | 本机 PATH 缺 `agent-reach`/`mcporter`/`opencli`/`bili`/`twitter`/`rdt`/`yt-dlp`/`gh` 等依赖 CLI，多数平台路由无法执行、`doctor --json` 自检也跑不了（环境依赖，技能文档本身完好） | t8 |
| B10 | onenote | 运行依赖 `mcp__onenote` MCP 服务器与 `onenote-mcp` CLI，本机与会话均未检出；正文已内置优雅降级与排查指引（环境依赖，正文无缺陷） | t7 |
| B11 | define-bounded-goal | `token_budget` 参数与 `token_budget_exhausted` 停止原因在当前 Goal 工具（`create_goal` 仅 objective/max_goal_rounds）中不存在，属 OpenAI 源技能参数漂移；另三层触发约束（无 disable-model-invocation / openai.yaml 禁隐式 / 正文要求 $ 显式调用）之间不一致 | t6 |

### C. 小问题（低危，一致性/卫生/文档失实）

| # | 对象 | 问题 | 来源 |
|---|---|---|---|
| C1 | reg-to-ll\workflow-run-skill | 嵌套 frontmatter `name: workflow-run` ≠ 目录名 `workflow-run-skill`（全域唯一 name 不一致项；当前仅作嵌套文档引用，无运行时影响） | t2/t5 |
| C2 | reg-to-ll\workflow-run-skill | "若用户只想检查已有文件，请使用对应的 check Skill"——该 check 技能本地不存在（悬空引用） | t5 |
| C3 | serial-debug | 目录含 `.venv/`、`build/`、`dist/`、`progress/` 等共 6,720 个文件（含 PySide6/Qt6 全套 DLL；windows/README 有意引用 .venv），体积与整洁度显著劣化 | t1/t2/t5 |
| C4 | serial-debug | `references/mcp.md` 未被 SKILL.md 或任何文件引用（孤立文档） | t5 |
| C5 | pack-to-dts | 文档称 `--output-dir` 默认 `D:\trash\Work\Innostar-ic\DTS`，实际 5 个脚本全部 `required=True` 无默认值 | t5 |
| C6 | pack-to-dts | description 面向自动触发（"只要涉及…就使用"），`agents/openai.yaml` 却设 `allow_implicit_invocation: false`，语气相悖 | t5 |
| C7 | pack-to-dts | `scripts/__pycache__/common.cpython-312.pyc` 残留 | t5 |
| C8 | reverse-engineer-anything | SKILL.md 支持客户端清单（15 个）落后于 `references/connection-and-recovery.md`（23 个） | t5 |
| C9 | andes-aice-bringup | 文档要求启动前校验端口 2354/4444/6666/9901 空闲，`start_aice.ps1` 只停进程不校验端口占用 | t5 |
| C10 | pyside6-fluent-ui | tests/、scripts/ 残留 `__pycache__`（8+ 个 .pyc）；`scripts/run_checks.sh` 为 shell 脚本，Windows 原生环境无入口说明 | t7 |
| C11 | ui-ux-pro-max | scripts/ 与 scripts/tests/ 残留 `__pycache__` | t7 |
| C12 | qt-ui-design | README Files 表仅列 SKILL.md，未列 LICENSE.txt | t7 |
| C13 | teach | `GLOSSARY-FORMAT.md` 存在但正文从未引用（孤儿支撑文件，glossary 格式约定缺入口） | t8 |
| C14 | game-dev、image-tools | description 触发信息弱（一句 "Personal-only … helpers"），且无 `agents/openai.yaml` | t8 |
| C15 | git-delivery | 正文内嵌本机安全组件拦截 `git push` 的症状与绕行方案，属机器特定运维知识，跨机复用需复核 | t6 |
| C16 | ask-matt | `/clear`、`/compact` 为 Claude Code 类 harness 命令，跨 harness 语义/可用性不同 | t8 |
| C17 | skills/ 根 | 散置非技能文件 `serial-debug.7z`（约 166 MB）与技能目录并存 | t1/t4 |
| C18 | workspace skills/ | 10 个裸 SKILL.md 技能（无 agents/、references/ 等任何支撑文件）：code-review、document-helper、find-skills、game-dev、git-delivery、git-helper、image-tools、internal-doc-search、jira-helper、python-helper（其中 6 个与 A/B 组占位/空壳问题重叠） | t1 |
| C19 | description 规范性 | 5 个超长 description（>400 字符：agent-reach 890、pyside6-fluent-ui 760、ui-ux-pro-max 495、serial-debug 423、andes-aice-bringup 401）；4 个块标量 description（agent-reach、cli-hub-meta-skill、pyside6-fluent-ui、qt-ui-design）——简易 frontmatter 提取器需支持块标量 | t1/t2 |
| C20 | 非标准 frontmatter 键 | 17 个技能含 `disable-model-invocation` 等；agent-reach 另有 `triggers`/`metadata`；hallmark 有 `argument-hint`/`version`；qt-ui-design 有 `license`/`compatibility`——可移植性取决于宿主是否识别 | t2 |
| C21 | reverse-engineer-anything | **t3 复核新发现**：工作区与 .agents 双副本 SKILL.md 内容漂移（工作区 23,865 B / 2026-10-23，.agents 23,523 B / 2026-10-21；差异为 .agents 版 frontmatter 多 `tool_count: 207`）。当前不影响使用（两版语义一致），但实证"双副本可能静默漂移" | t3 复核 |

### D. 建议项（配置 / 依赖 / 观察项）

| # | 对象 | 内容 | 来源 |
|---|---|---|---|
| D1 | triage、to-spec、to-tickets、run-tickets（wayfinder 间接） | 共同依赖一次性 `/setup-matt-pocock-skills` 写入的仓库配置（tracker + 标签 + 领域文档）；本工作区从未运行（无 `docs/` 目录）。前三者有兜底指引，run-tickets 无 | t6 |
| D2 | 环境依赖 | `gh`（setup GitHub 路线、wizard、agent-reach）；7-Zip（pack-to-dts 缺失时会从 7-zip.org 下载 7zr.exe，内网会失败）；OneNote MCP；agent-reach 后端 CLI——离线/内网环境需提前离线部署 | t5/t7/t8 |
| D3 | 外部网络依赖登记 | serial-debug 的 GitHub 仓库同步入口、reverse-engineer-anything 的 morluto/rea 文档链接、find-skills 的 skills.sh 排行榜——离线不可验证，非技能缺陷 | t5/t8 |
| D4 | 工具链 | 中文技能 frontmatter 为 UTF-8（t2 曾因 GBK 误读出现乱码，已复核文件无损）——审计/解析工具链需显式 UTF-8 | t2 |
| D5 | 范围外登记 | `skills/` 之外全域仅 2 处散落 SKILL.md（`projects/xerj` 下 xerj-security-audit、xerj-code），属 vendored XERJ 仓库自带，非技能库成员，无需处理 | t1 |

## ⑤ 建议（按优先级）

**P1 — 影响实际使用，建议尽快处理**

1. **占位/空壳技能处置**（A 组 + B6/B7/B8）：code-review、git-helper、python-helper 要么扩写真实内容，要么把 description 改为与 game-dev/image-tools 一致的示例技能定位；document-helper、jira-helper、internal-doc-search 若需真实能力则补写具体模板/工作流，否则在装配层明确标注"示例，非交付能力"（tdd/implement 引用 code-review 作收尾环节，随其扩写自动改善）。
2. **reg-to-ll 飞书链路**（B1）：安装 `feishu-fetch` 技能，或在 `workflow-run-skill/SKILL.md` 注明"飞书输入需先具备该技能"及替代获取方式；本地 Excel 链路可正常使用，不受影响。
3. **run-tickets 路径与配置**（B4/B5）：把 `docs/agents/issue-tracker.md` 的引用改为条件式（"if present, … otherwise run /setup-matt-pocock-skills"）；helper 路径改为相对 SKILL.md 自身位置解析，或注明"工作区与 ~\.agents 两副本需保持同步"。
4. **ui-ux-pro-max 指引**（B2/B3）：补一个含安装说明的 README.md（或删除空引用改为内联说明），并在 SKILL.md 注明脚本按实际技能根目录解析。
5. **运行一次 `/setup-matt-pocock-skills`**（D1）：完成 issue tracker、triage 标签、领域文档配置，解锁 triage、to-spec、to-tickets、run-tickets、wayfinder 的完整功能。

**P2 — 一致性与卫生，建议随后处理**

6. **统一嵌套技能名**（C1/C2）：`workflow-run` ↔ `workflow-run-skill` 二选一改名（注意同步 `.reg-to-ll-install.json` 清单），并补齐或删除 check Skill 悬空引用。
7. **define-bounded-goal 参数修订**（B11）：删除或改写 `token_budget`/`token_budget_exhausted` 两处为当前 Goal 工具实际支持的维度（如 max_goal_rounds），并补 `disable-model-invocation: true` 或在 description 写明显式调用要求。
8. **目录卫生**（C3/C4/C7/C10/C11/C17）：移出 `skills/serial-debug.7z`；将 serial-debug 的 `.venv/build/dist` 视为本地运行时移出技能目录或加入忽略清单；清理 pyside6-fluent-ui、ui-ux-pro-max、pack-to-dts、serial-debug 的 `__pycache__`；serial-debug 的 `references/mcp.md` 收编进 SKILL.md References 或删除。
9. **文档-实现对齐**（C5/C8/C9/C12/C13）：pack-to-dts 修正 output-dir 参数表（标"必填"或脚本补默认值）；reverse-engineer-anything 同步两处客户端清单（以较新的 23 个为准）；andes-aice-bringup 在启动脚本补端口校验或修改文档措辞；qt-ui-design README 补列 LICENSE.txt；teach 正文补 `[GLOSSARY-FORMAT.md](./GLOSSARY-FORMAT.md)` 链接。
10. **触发策略确认**（C6/C14）：pack-to-dts 确认隐式调用禁用是否刻意（刻意则软化 description 强触发语气）；game-dev/image-tools 若要真实启用需补触发词并核实环境装配。

**P3 — 三处同步与观察项，按需处理**

11. **双副本同步机制**（C21 + ②矩阵）：工作区 `skills/` 与 `~\.agents\skills` 有 45 个同名技能，SKILL.md 哈希比对 44/45 一致（reverse-engineer-anything 漂移）。建议明确"哪一处是主库"（当前会话可见集以 .agents 为主），并决定 cli-anything、cli-hub-meta-skill、hallmark（仅 .agents）与 game-dev、image-tools、internal-doc-search（仅工作区）是否双向同步；今后更新技能时两处副本一起更新。
12. **hatch-pet 可见性确认**（③）：该用户层 Codex 技能磁盘有效但当前会话不可见，确认是否符合预期；如需在本 harness 使用，需查明宿主对 `~\.codex\skills` 用户层的装载策略。
13. **环境依赖装配**（B9/B10 + D2）：按需安装 agent-reach 后端 CLI、OneNote MCP、`gh`、7-Zip；离线/内网环境提前离线部署（pack-to-dts 的 7zr.exe 下载在内网会失败）。
14. **description 规范化观察**（C19/C20）：如后续统一规范，关注超长 description 的触发词密度、块标量解析器支持、非标准 frontmatter 键的跨宿主可移植性。

---

**附注**：`dist/agent-workspace-v0.1.0-offline/workspace/skills/` 是离线分发包快照，做目录名集合级对比即可——t3 只读复核结果：**快照与工作区 skills/ 的目录名集合不一致**：dist 含 45 个技能目录（全树 46 个 SKILL.md = 45 顶层 + 1 嵌套 workflow-run-skill），较工作区 48 个**缺 `find-skills`、`reverse-engineer-anything`、`ui-ux-pro-max` 3 个目录**；dist 根目录无 `serial-debug.7z`。其余 45 个目录名与工作区一致。该快照已落后于工作区，如需作为分发基线应重新生成或补齐。

## 附：来源与统计口径

- 深读覆盖 = 工作区 48/48 技能（t5 嵌入式 6 + t6 开发流程 15 + t7 设计/文档 10 + t8 元技能/杂项 17）。`~\.agents\skills` 的 45 个同名目录未逐一深读，以工作区副本深读结论为代表（本轮哈希比对 44/45 一致，1 处漂移已登记）；仅 .agents 的 3 个技能与 .codex 侧 7 个技能仅经 t2 结构审计。
- 可用度统计以各分类报告**逐技能结论表**为准：可用 36 / 基本可用 9 / 不可用 3。注：t6 摘要行按 13/2 口径（将 run-tickets、define-bounded-goal 记为"可用"），其明细表标为"基本可用（有小问题）"；本报告以明细表为准，差异仅为"有小问题"技能的归档口径，不影响总体结论。
- 全部审计为只读静态检查（未运行技能/脚本/Git 命令）；"可执行/可用"判断基于文本完整性、支撑文件真实性与引用一致性。各分类报告的独立审计局限见原文件（t6/t7/t8 尾节）。
