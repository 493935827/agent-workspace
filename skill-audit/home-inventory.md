# 用户目录技能审计清单（home-inventory）

- 审计任务：t2 [t-home-audit]（审计人：home-auditor）
- 审计时间：2026-11-02 17:36
- 审计对象：
  1. `C:\Users\E0465\.agents\skills`（48 个技能目录）
  2. `C:\Users\E0465\.codex\skills`（2 个顶层条目：`.system`、`hatch-pet`）
- 审计方式：只读。逐目录检查 SKILL.md 存在性、frontmatter（name/description 及额外键）、name 与目录名一致性、SKILL.md 正文非空、支撑文件构成、嵌套 SKILL.md。
- 表格列：目录名 | SKILL.md（✓=存在，附字节数）| frontmatter name | 与目录名一致 | description 摘要 | 备注

## 一、C:\Users\E0465\.agents\skills（48 个技能目录）

统计：48/48 存在 SKILL.md；48/48 frontmatter 含 name 与 description；48/48 name 与目录名一致；48/48 正文非空；根目录无散落文件；36/48 带 `agents/openai.yaml`（接口元数据：display_name/short_description/default_prompt 或 icons）；0 个根级嵌套 SKILL.md，1 个深层嵌套技能（见"三、嵌套技能"）。

| 目录名 | SKILL.md | frontmatter name | 与目录名一致 | description 摘要 | 备注 |
|---|---|---|---|---|---|
| agent-reach | ✓ 6.2KB | agent-reach | ✓ | MUST USE when user wants to 调研/research/搜索/查 anything on the internet…15 platforms, multi-backend routing | agents/openai.yaml、references/；额外键 triggers、metadata；description 为 YAML 块标量(>)，含中文触发词表 |
| andes-aice-bringup | ✓ 4.3KB | andes-aice-bringup | ✓ | Bring up and diagnose Andes AICE/ICEman on Windows when USB cannot open… | agents/、references/、scripts/ |
| ask-matt | ✓ 11.6KB | ask-matt | ✓ | Ask which skill or flow fits your situation. A router over the skills in this repo. | agents/、PHASE-BOUNDARIES.md；额外键 disable-model-invocation |
| cli-anything | ✓ 6.2KB | cli-anything | ✓ | Use when the user wants Codex to build, refine, test, validate, or list CLI-Anything harnesses… | agents/、references/、scripts/、tests/（共 24 文件） |
| cli-hub-meta-skill | ✓ 5.5KB | cli-hub-meta-skill | ✓ | Discover agent-native CLIs for professional software. Access the live catalog… | 仅 SKILL.md；description 为块标量(>-) |
| code-review | ✓ 0.6KB | code-review | ✓ | Structured code review - correctness, style, and tests. | 仅 SKILL.md；正文自述 "Example skill … MVP / Placeholder content"（占位示例技能） |
| codebase-design | ✓ 6.6KB | codebase-design | ✓ | Shared vocabulary for designing deep modules… | agents/、DEEPENING.md、DESIGN-IT-TWICE.md |
| define-bounded-goal | ✓ 14.6KB | define-bounded-goal | ✓ | Define or refine a concrete, measurable Goal with an explicit wall-clock timebox… | agents/ |
| diagnosing-bugs | ✓ 9.1KB | diagnosing-bugs | ✓ | Diagnosis loop for hard bugs and performance regressions… | agents/、scripts/ |
| document-helper | ✓ 0.4KB | document-helper | ✓ | Company document drafting and formatting helpers. | 仅 SKILL.md；MVP 示例技能，正文引用 `configs/company.yaml` |
| domain-modeling | ✓ 3.5KB | domain-modeling | ✓ | Build and sharpen a project's domain model… | agents/、ADR-FORMAT.md、CONTEXT-FORMAT.md |
| find-skills | ✓ 7.5KB | find-skills | ✓ | Helps users discover and install agent skills… | 仅 SKILL.md |
| firmware-mentor | ✓ 6.3KB | firmware-mentor | ✓ | 面向初级固件与嵌入式工程师的中文技术导师。 | agents/、references/；额外键 disable-model-invocation（仅用户显式调用） |
| git-delivery | ✓ 6.2KB | git-delivery | ✓ | 完成 Bug 修复、项目文件或技能修改时使用：…自动 Git 提交，并在已授权的远程目标上推送（中文技能） | 仅 SKILL.md |
| git-helper | ✓ 0.6KB | git-helper | ✓ | Everyday git helpers - branch hygiene, commit messages, safe undo. | 仅 SKILL.md；MVP 示例/占位技能，正文含 "Update note (simulated edit on personal machine)" 测试性段落 |
| grill-me | ✓ 0.2KB | grill-me | ✓ | A relentless interview to sharpen a plan or design. | agents/；正文仅一行 "Run a `/grilling` session."（薄包装技能） |
| grill-with-docs | ✓ 0.3KB | grill-with-docs | ✓ | A relentless interview…which also creates docs (ADR's and glossary) as we go. | agents/；正文一行，指向 /grilling + /domain-modeling（薄包装技能） |
| grilling | ✓ 3.1KB | grilling | ✓ | Grill the user relentlessly about a plan, decision, or idea… | agents/ |
| hallmark | ✓ 18.2KB | hallmark | ✓ | Design skill for websites and new pages that look designed, not generated… | agents/、LICENSE、references/、scripts/（共 166 文件）；额外键 argument-hint、version、metadata |
| handoff | ✓ 15.1KB | handoff | ✓ | Archive the current conversation, provide an early-start continuation prompt, maintain progress index… | agents/；额外键 argument-hint、disable-model-invocation |
| implement | ✓ 0.4KB | implement | ✓ | Implement a piece of work based on a spec or set of tickets. | agents/；正文为编排指引（/tdd、/code-review、提交分支） |
| improve-codebase-architecture | ✓ 6.1KB | improve-codebase-architecture | ✓ | Scan a codebase for deepening opportunities, present them as a visual HTML report… | agents/、HTML-REPORT.md |
| jira-helper | ✓ 0.4KB | jira-helper | ✓ | Company Jira workflow helpers (tickets, sprints, queries). | 仅 SKILL.md；MVP 示例技能，要求 `COMPANY_TOKEN` secret |
| onenote | ✓ 4.7KB | onenote | ✓ | Operate Microsoft OneNote through the `mcp__onenote` MCP tools… | agents/ |
| pack-to-dts | ✓ 4.6KB | pack-to-dts | ✓ | 下载任意类型的文件/包并打包为 7z 离线压缩包…（中文技能） | .gitignore、agents/、scripts/ |
| project-structure | ✓ 6.0KB | project-structure | ✓ | 在初始化项目、规划目录和文档结构…时使用（中文技能） | agents/、references/ |
| prototype | ✓ 3.0KB | prototype | ✓ | Build a throwaway prototype to answer a design question… | agents/、LOGIC.md、UI.md |
| pyside6-fluent-ui | ✓ 17.8KB | pyside6-fluent-ui | ✓ | Build, audit, and incrementally refactor PySide6/Qt Widgets desktop interfaces using Fluent 2… | agents/、examples/、LICENSE、NOTICE.md、references/、resources/、scripts/、SHA256SUMS、templates/、tests/、VERSION（共 80 文件）；description 为块标量(>) |
| python-helper | ✓ 0.5KB | python-helper | ✓ | Python idioms, packaging and debugging snippets. | 仅 SKILL.md；MVP 示例/占位技能 |
| qt-ui-design | ✓ 25.5KB | qt-ui-design | ✓ | Design or audit UI for Qt/QML, Qt projects, web, or embedded MPU or MCU targets… | LICENSE.txt、README.md；额外键 license、compatibility、disable-model-invocation、metadata；description 为块标量(>-) |
| reg-to-ll | ✓ 0.6KB | reg-to-ll | ✓ | 将本地 Excel 或离线飞书快照经过强制验证，生成可追溯的 SVD、CMSIS 头文件和 LL Driver（中文技能） | 正文仅 10 行，委托嵌套 `workflow-run-skill/`；另含 .reg-to-ll-install.json、compatibility/、3 个 Python 模块 |
| research | ✓ 0.8KB | research | ✓ | Investigate a question against high-trust primary sources… | agents/；正文为后台 agent 研究指引（12 行） |
| resolving-merge-conflicts | ✓ 0.9KB | resolving-merge-conflicts | ✓ | Use when you need to resolve an in-progress git merge/rebase conflict. | agents/ |
| reverse-engineer-anything | ✓ 23.5KB | reverse-engineer-anything | ✓ | Reverse engineer native, managed, Electron/JavaScript, packaged, firmware, and browser targets with REA… | references/；额外键 metadata |
| run-tickets | ✓ 12.9KB | run-tickets | ✓ | Run a Matt Pocock /to-tickets set in Codex as dependency-aware waves… | agents/、references/、scripts/；额外键 disable-model-invocation |
| serial-debug | ✓ 8.9KB | serial-debug | ✓ | Shared serial console debugging for Codex and Claude Code… | ⚠ 共 6720 文件：.venv/、build/、dist/ 等工程/虚拟环境产物混入技能目录；另有 AGENTS.md、README.md、SerialWorkbench.spec、docs/、progress/、tests/、windows/、.gitignore |
| setup-matt-pocock-skills | ✓ 7.0KB | setup-matt-pocock-skills | ✓ | Configure this repo for the engineering skills — set up issue tracker, triage label vocabulary… | agents/、domain.md、issue-tracker-{github,gitlab,local}.md、triage-labels.md |
| tdd | ✓ 3.6KB | tdd | ✓ | Test-driven development…red-green-refactor… | agents/、mocking.md、tests.md |
| teach | ✓ 9.6KB | teach | ✓ | Teach the user a new skill or concept, within this workspace. | agents/、GLOSSARY-FORMAT.md、LEARNING-RECORD-FORMAT.md、MISSION-FORMAT.md、RESOURCES-FORMAT.md；额外键 disable-model-invocation、argument-hint |
| to-questionnaire | ✓ 3.0KB | to-questionnaire | ✓ | Turn a decision you can't fully answer into a questionnaire… | agents/ |
| to-spec | ✓ 3.1KB | to-spec | ✓ | Turn the current conversation into a spec and publish it to the project issue tracker… | agents/ |
| to-tickets | ✓ 5.8KB | to-tickets | ✓ | Break a plan, spec, or the current conversation into a set of tracer-bullet tickets… | agents/ |
| triage | ✓ 6.7KB | triage | ✓ | Move issues and external PRs through a state machine of triage roles… | agents/、AGENT-BRIEF.md、OUT-OF-SCOPE.md |
| ui-ux-pro-max | ✓ 16.2KB | ui-ux-pro-max | ✓ | UI/UX design intelligence for web, mobile, and desktop… | data/、references/、scripts/（共 90 文件：79 styles、192 palettes、74 font pairings 等本地数据） |
| wait-what | ✓ 0.3KB | wait-what | ✓ | Stop. That last message did not land — re-pitch it. | agents/；正文一行（要求以 ASD-STE100 简明英语 + `CONTEXT.md` 术语重述） |
| wayfinder | ✓ 12.0KB | wayfinder | ✓ | Plan a huge chunk of work…as a shared map of decision tickets on your issue tracker… | agents/ |
| wizard | ✓ 4.2KB | wizard | ✓ | Generate an interactive bash wizard that walks a human through steps only they can perform… | agents/、template.sh |
| writing-for-agents | ✓ 11.0KB | writing-for-agents | ✓ | Writing documents for agents…modifying AGENTS.md or CLAUDE.md | agents/、SKILL-MECHANICS.md |

## 二、C:\Users\E0465\.codex\skills（2 个顶层条目）

结论：
- `hatch-pet` 是**有效技能**：完整结构（SKILL.md 37.3KB/539 行 + agents/openai.yaml + references + scripts + LICENSE），frontmatter name 与目录名一致，正文详尽。其定位是"创建/修复/验证/视觉 QA/打包 Codex 兼容动画宠物与宠物 spritesheet"的工作流技能，显式组合本目录 `.system/imagegen`（`$imagegen`）做视觉生成，自带 9 个 Python 脚本做确定性的 atlas 几何、校验与打包。
- `.system` **本身不是技能**，而是 Codex 内置系统技能目录（`~\.codex\skills\.system`），内含 **6 个全部有效的内置技能**（每个都有 SKILL.md + agents/openai.yaml，name 与目录一致），外加一个非技能的标记文件 `.codex-system-skills.marker`（内容为 ID `eb8751f4456f448a`）。

| 目录名 | SKILL.md | frontmatter name | 与目录名一致 | description 摘要 | 备注 |
|---|---|---|---|---|---|
| .system | —（非技能目录） | — | — | — | Codex 内置系统技能集合，见下表；marker 文件 `.codex-system-skills.marker`（17B，ID `eb8751f4456f448a`）为系统技能目录标记，非技能 |
| hatch-pet | ✓ 37.3KB | hatch-pet | ✓ | Create, repair, validate, visually QA, and package Codex-compatible animated pets and pet spritesheets… | 用户自装技能；agents/openai.yaml（display_name "Hatch Pet"）、references/（animation-rows.md、codex-pet-contract.md、qa-rubric.md）、scripts/（9 个 Python 脚本）、LICENSE.txt；依赖 `.system/imagegen`（$imagegen） |

### .system 内置技能（6 个）

| 目录名 | SKILL.md | frontmatter name | 与目录名一致 | description 摘要 | 备注 |
|---|---|---|---|---|---|
| .system/imagegen | ✓ 19.5KB | imagegen | ✓ | Generate or edit raster images when the task benefits from AI-created bitmap visuals… | 内置；agents/openai.yaml、assets/（svg+png）、references/（5 篇）、scripts/（2 个 py）、LICENSE.txt |
| .system/openai-docs | ✓ 5.5KB | openai-docs | ✓ | Use for Codex models/pricing, scheduled tasks, skills, settings…self-knowledge… | 内置；agents/openai.yaml、assets/、references/（9 篇）、scripts/（mjs/cjs/无扩展名 runner）、LICENSE.txt；额外键 metadata |
| .system/plugin-creator | ✓ 11.7KB | plugin-creator | ✓ | Create and scaffold plugin directories for Codex with a required `.codex-plugin/plugin.json`… | 内置；agents/openai.yaml、assets/、references/、scripts/（5 个 py）；无 LICENSE |
| .system/review-agent | ✓ 2.7KB | review-agent | ✓ | Perform a read-only, defect-first review of a specified code change… | 内置；仅 SKILL.md + agents/openai.yaml（最简结构） |
| .system/skill-creator | ✓ 15.5KB | skill-creator | ✓ | Create or update a Codex skill with appropriately scoped instructions… | 内置；agents/openai.yaml、assets/、references/（openai_yaml.md）、scripts/（init/validate/generate 3 个 py）、license.txt；额外键 metadata |
| .system/skill-installer | ✓ 3.4KB | skill-installer | ✓ | Install Codex skills into $CODEX_HOME/skills from a curated list or a GitHub repo path… | 内置；agents/openai.yaml、assets/、scripts/（3 个 py）、LICENSE.txt；额外键 metadata |

## 三、嵌套技能（全部审计对象中仅 1 处）

| 嵌套路径 | SKILL.md | frontmatter name | 与目录名一致 | description 摘要 | 备注 |
|---|---|---|---|---|---|
| .agents/skills/reg-to-ll/workflow-run-skill | ✓ 3.3KB | workflow-run | ✗（name 缺 `-skill` 后缀，与目录名不同） | 通过稳定的可执行 runner，将本地 Excel 或离线飞书快照依次转换为 SVD、ae350.h 和 LL Driver（中文技能） | 嵌套在 reg-to-ll 内部、不会被顶层扫描当作独立技能；被 reg-to-ll 主 SKILL.md 作为"工作流契约"文档引用；frontmatter 额外含 prerequisites（python>=3.8、openpyxl、SVDConv、Oracle manifest）与 language: zh-CN；同目录有 reference.md、run_workflow.py |

## 四、问题汇总

结构完整性结论：`.agents\skills` 48 个技能目录 **100% 通过基础结构检查**（SKILL.md 存在、frontmatter name/description 齐全、name 与目录名一致、正文非空）；`.codex\skills` 两个顶层条目均已查明且均为有效技能/有效技能集合。未发现缺失 SKILL.md、空 frontmatter 或 name 不一致的顶层技能。以下为非阻断性问题与观察项：

1. 【中】**嵌套技能 name 与目录名不一致**：`reg-to-ll/workflow-run-skill` 的 frontmatter `name: workflow-run` ≠ 目录名。当前仅作嵌套文档引用，无运行时影响；若将来被提升为顶层技能目录，会产生 name/目录名不匹配。
2. 【低】**serial-debug 目录结构污染**：含 `.venv/`、`build/`、`dist/` 等共 6720 个文件，虚拟环境与打包产物混入技能目录，显著偏离其他技能的轻量结构（只读审计，未清理）。
3. 【低】**MVP 示例/占位技能混入**：`code-review`、`document-helper`、`jira-helper`、`python-helper`、`git-helper` 共 5 个，正文自述 "Example skill / Placeholder content: replace with your real skill"；`git-helper` 还带 "Update note (simulated edit on personal machine)" 测试性段落。它们与真实技能并列展示，易与正式技能混淆。
4. 【低】**块标量 description**：`agent-reach`(>)、`cli-hub-meta-skill`(>-)、`pyside6-fluent-ui`(>)、`qt-ui-design`(>-) 共 4 个使用 YAML 块标量。结构合法，但简易 frontmatter 提取器（按单行匹配）会取不到内容——审计工具链需支持块标量。
5. 【低】**非标准/扩展 frontmatter 键**：17 个技能含 `disable-model-invocation`；agent-reach 另有 `triggers`；hallmark 有 `argument-hint`/`version`；qt-ui-design 有 `license`/`compatibility`；多个技能含 `metadata`。超出 name/description 最小约定，可移植性取决于宿主是否识别。
6. 【信息】`.agents\skills` 36/48 携带 `agents/openai.yaml`（抽样验证均为仅此一个文件），是 Codex 技能的接口元数据约定（display_name/short_description/default_prompt 或 icons）。
7. 【信息】`hatch-pet` 与 `.system` 的 6 个内置技能构成 `~\.codex\skills` 全部内容；`.codex-system-skills.marker`（ID `eb8751f4456f448a`）为系统标记文件，非技能。
8. 【信息】中文技能（firmware-mentor、git-delivery、pack-to-dts、project-structure、reg-to-ll 及嵌套 workflow-run-skill）的 frontmatter 均为 UTF-8 中文，内容读取正常（审计中曾因 GBK 误读出现乱码，已用显式 UTF-8 复核确认文件本身无损）。

## 五、三处存在性差异待比对项（供 captain/后续比对任务使用）

本清单仅覆盖用户目录两处；与工作区 `skills/` 的存在性差异比对由相应任务完成。为比对方便列出关键交集/独有点：

- `.agents\skills` 独有（工作区 skills/ 需核对是否缺失）：andes-aice-bringup、ask-matt、cli-anything、cli-hub-meta-skill、define-bounded-goal、diagnosing-bugs、document-helper、domain-modeling、find-skills、firmware-mentor、git-delivery、git-helper、grill-me、grill-with-docs、grilling、hallmark、handoff、implement、improve-codebase-architecture、jira-helper、onenote、pack-to-dts、project-structure、prototype、pyside6-fluent-ui、python-helper、qt-ui-design、reg-to-ll、research、resolving-merge-conflicts、reverse-engineer-anything、run-tickets、serial-debug、setup-matt-pocock-skills、tdd、teach、to-questionnaire、to-spec、to-tickets、triage、ui-ux-pro-max、wait-what、wayfinder、wizard、writing-for-agents、agent-reach、code-review、codebase-design（共 48，最终以 t1 的 ws-inventory 为准比对）
- `.codex\skills` 侧：hatch-pet 与 6 个 .system 内置技能（imagegen、openai-docs、plugin-creator、review-agent、skill-creator、skill-installer）在另外两处目录中均无对应目录。
- 会话可见技能差异线索：本会话可用技能目录录中出现了 openai-docs、imagegen、plugin-creator、review-agent、skill-creator、skill-installer（来自 .system）与 hatch-pet 未见列出——hatch-pet 未出现在本会话技能目录中，属"目录存在但会话不可见"现象，供差异分析参考。
