# 分类深读审计：Agent 元技能与工具杂项类（17 个）

- 审计对象：`D:\App\agent-workspace\skills\` 下 agent-reach、ask-matt、find-skills、game-dev、grill-me、grill-with-docs、grilling、handoff、image-tools、project-structure、python-helper、setup-matt-pocock-skills、teach、wait-what、wayfinder、wizard、writing-for-agents。
- 审计方式：逐个完整读取 SKILL.md 正文（非仅 frontmatter）；逐个核对正文引用的相对路径支撑文件是否真实存在；对引用的外部命令在本会话 PATH 中实测（`Get-Command`）；交叉核对 configs/、agentctl/、local.yaml 等被引用的工作区事实。
- 约束遵守：只读审计，唯一写入文件为本报告；未修改任何技能内容，未触碰 dist\。
- 严重程度分级：高 / 中 / 低 / 信息。

## 总览

| 检查项 | 结果 |
| --- | --- |
| frontmatter name 与目录名一致 | 17/17 一致 |
| description 存在 | 17/17 存在 |
| 正文完整（无 TODO/占位/截断） | 16/17（python-helper 正文自述占位） |
| 引用的支撑文件全部存在 | 16/17（teach 的 GLOSSARY-FORMAT.md 存在但未被正文引用，属孤儿文件） |
| 引用的外部命令/工具 | agent-reach 依赖的多数 CLI 本机未安装（详见各节） |
| 会话可见性 | 10 个不在会话技能目录中：8 个因 `disable-model-invocation: true`（设计使然），game-dev / image-tools 为环境排除的示例技能 |

**总体结论：可用 14 / 基本可用有小问题 3 / 不可用 0。**

---

## 1. agent-reach

- **frontmatter**：`name: agent-reach` 与目录一致；description 详尽——中英双语触发场景（调研/搜索/平台名/URL）、15 平台清单、NOT for 边界（不做内容加工、不做写操作、让位专门 skill）、路由方式说明，触发描述质量为 17 个中最好。额外含非标准字段 `triggers`（嵌套映射）与 `metadata.openclaw.homepage`，部分 harness 会忽略，无害。
- **正文完整性**：完整。常驻规则（先 doctor 体检、声明后端、失败走 references 重试链、多平台并行、替用户盯版本）、路由表、零配置命令、登录态命令组、环境检查、工作区规则（/tmp 与 ~/.agent-reach/）、详细文档索引、配置渠道。无 TODO、无占位、无截断。
- **支撑文件**：正文链接的 6 个 references 全部存在且有实质内容——`references/search.md`(33 行)、`social.md`(275 行)、`career.md`(29 行)、`dev.md`(62 行)、`video.md`(131 行)、`web.md`(50 行)；路径与路由表逐一对应。`agents/openai.yaml` 存在。
- **过时/失效**：本会话 PATH 实测 `agent-reach`、`mcporter`、`opencli`、`bili`、`twitter`、`rdt`、`yt-dlp`、`gh` **均未安装**——技能自身 CLI 不在 PATH 意味着 `doctor --json` 体检也跑不了；本机仅 curl 类通道（r.jina.ai 网页阅读、V2EX API）可直接使用。外部安装/更新链接（github.com/Panniantong/agent-reach 的 docs/install.md、update.md）未逐一验证可达。
- **评价**：**基本可用有小问题**——技能结构完好、文档齐备且自检设计合理，但本机缺少其依赖的绝大部分命令后端，多数平台路由无法实际执行。

## 2. ask-matt

- **frontmatter**：`name` 一致；description 简短但定位明确（"Ask which skill or flow fits your situation. A router over the skills in this repo"）；`disable-model-invocation: true`（手动调用的路由器，符合"人记不住技能时来问"的设计，SKILL-MECHANICS.md 中称这类为 router skill）。
- **正文完整性**：完整。主流程 idea→ship、分支（原型/handoff、多会话拆票）、上下文卫生（smart zone ~150k）、三个 on-ramps（triage、diagnosing-bugs、wayfinder）、代码库健康、词汇层（domain-modeling、codebase-design）、阶段边界、Standalone 清单、前置条件 setup-matt-pocock-skills。无 TODO/截断。
- **支撑文件**：`PHASE-BOUNDARIES.md` 存在（55 行），内容与正文"五选项+判定树+主次来源"一致。正文点名的全部 24 个 `/技能`（grill-with-docs、grill-me、grilling、handoff、prototype、to-spec、to-tickets、implement、tdd、code-review、triage、diagnosing-bugs、improve-codebase-architecture、wayfinder、codebase-design、domain-modeling、resolving-merge-conflicts、research、to-questionnaire、wizard、wait-what、teach、writing-for-agents、setup-matt-pocock-skills）逐一核对均存在于本仓库 skills/ 目录。
- **过时/失效**：`/clear`、`/compact` 为 Claude Code 类 harness 命令，在其他 harness 中语义/可用性不同（PHASE-BOUNDARIES 自身已承认跨 harness 视角，"swapping to a new harness (Claude → Codex)"）；属移植技能组的固有前提，非缺陷。
- **评价**：**可用**。

## 3. find-skills

- **frontmatter**：`name` 一致；description 清楚列出触发问法（"how do I do X"/"find a skill for X"/"is there a skill that can..."）。无 `agents/openai.yaml`（17 个中 4 个没有之一；与其上游 vercel-labs/skills 来源一致，非缺陷）。
- **正文完整性**：完整。六步流程（理解需求→看排行榜→搜索→质量核验→呈现→安装）+ 常见类别表 + 搜索技巧 + 无结果处理。无 TODO/截断。
- **支撑文件**：无本地文件引用（纯正文技能），与目录内容一致（仅 SKILL.md）。
- **过时/失效**：无失效。末尾"本环境适配"节声称 `skills` CLI 已全局安装——实测 PATH 中确有 `skills.ps1`（dsh-offline node 目录），`~/.agents/skills/` 与 `~/.codex/skills/` 均存在，`-a pi` 安装目标路径约定与实际目录结构相符；`DISABLE_TELEMETRY=1`、内网离线限制等说明自洽。上游 skills.sh 排行榜为外部服务，离线不可验证。
- **评价**：**可用**。

## 4. game-dev

- **frontmatter**：`name` 一致；description "Personal-only game development helpers (engines, assets)"——存在但触发信息弱，依赖正文 When to use 补充。无 `agents/openai.yaml`。
- **正文完整性**：完整但极简（19 行），自我定位明确："Example skill for the `personal` environment"。作为示例/占位技能而言没有缺失内容。
- **支撑文件**：无本地文件引用；正文声明的两个配置事实**逐一核实为真**——`configs/personal.yaml` 确实启用 game-dev，`configs/company.yaml` 的 `exclude_skills` 确实列有 game-dev。
- **过时/失效**：无。本机 local.yaml 解析为 `environment: company`，按其自身声明本机应被排除——与会话技能目录中不可见的事实相符。
- **评价**：**可用**（作为示例技能完整自洽；会话不可见属环境排除的预期行为）。

## 5. grill-me

- **frontmatter**：`name` 一致；description 明确（"A relentless interview to sharpen a plan or design"）；`disable-model-invocation: true`。
- **正文完整性**：正文仅一行 "Run a `/grilling` session."——这是刻意的包装技能（无状态入口），非截断；ask-matt 对其 stateless 定位有完整说明。
- **支撑文件**：依赖的 `/grilling` 技能存在；无本地文件引用；`agents/openai.yaml` 存在。
- **过时/失效**：无。
- **评价**：**可用**。

## 6. grill-with-docs

- **frontmatter**：`name` 一致；description 明确并说明差异点（"also creates docs (ADR's and glossary) as we go"）；`disable-model-invocation: true`。
- **正文完整性**：正文一行 "Run a `/grilling` session, using the `/domain-modeling` skill."——与 grill-me 同构的包装技能，完整非截断。
- **支撑文件**：`/grilling`、`/domain-modeling` 均存在；`agents/openai.yaml` 存在。
- **过时/失效**：无。
- **评价**：**可用**。

## 7. grilling

- **frontmatter**：`name` 一致；description 含明确触发（stress-test thinking、"grill" trigger phrases）；模型可见（无 disable-model-invocation），与会话技能目录在列一致。
- **正文完整性**：完整。设计树、轮次与 frontier 规则、每轮未决决策盘点（ready/blocked 分类）、问题格式模板（❓Q1/➡️推荐答案）、事实找 agent/决策问用户的分工、结束条件（frontier 清空）。无 TODO/截断。
- **支撑文件**：无本地文件引用；`agents/openai.yaml` 存在。
- **过时/失效**：无。"Use the permitted question interface that can present the complete frontier; if its per-call limit requires multiple batches…" 的措辞已做 harness 中立化，与当前环境的分批提问机制吻合。
- **评价**：**可用**。

## 8. handoff

- **frontmatter**：`name` 一致；description 长但覆盖全部职责（归档、提前续接提示、progress 索引、git 提交推送、内网约束），触发充分；`argument-hint` 与 `disable-model-invocation: true` 齐备。
- **正文完整性**：完整（121 行）。定位读取、提前续接提示、归档撰写规则、progress.md 三层渐进披露结构（含模板）、AGENTS.md 导航规则、验证与上传（offline zone 判定、远端选择、范围化暂存）、Conventional Commits 格式、返回内容。无 TODO/截断。
- **支撑文件**：无本地文件引用；正文引用的运行时事实**全部核实**：工作区根 `local.yaml` 存在且含 `environment: company`、`AGENT_WORKSPACE_ROOT` 已设置、`agentctl/` 模块存在、`configs/intranet.yaml` 确有 `network.internet: false`（offline zone 定义准确）。`AGENTCTL_ENV` 本会话为空，但技能的回退链（env → local.yaml）已覆盖。`wait_threads`/`read_thread` 用 "when available" 措辞，harness 无关化处理妥当。
- **过时/失效**：无。
- **评价**：**可用**。

## 9. image-tools

- **frontmatter**：`name` 一致；description "Personal-only image processing and generation helpers"——存在但触发信息弱。无 `agents/openai.yaml`。
- **正文完整性**：完整但极简（18 行），同 game-dev 的示例技能定位。
- **支撑文件**：配置事实核实为真——`configs/personal.yaml` 启用、`configs/intranet.yaml` 的 `exclude_skills` 确列 image-tools，与正文声明一致。
- **过时/失效**：无。注：本机为 company 环境，company.yaml 未排除 image-tools（仅排除 game-dev），而会话目录中该技能同样不可见——具体原因属环境装配/可见性差异任务的比对范围，本节仅记录事实。
- **评价**：**可用**（作为示例技能）。

## 10. project-structure

- **frontmatter**：`name` 一致；中文 description 触发与排除边界写得清楚（何时触发、普通内容修改/只读任务/单文件创建不触发、不自动调用 handoff）；模型可见，与会话目录在列一致。
- **正文完整性**：完整。触发与范围、定位按需读取、文件归属职责表（README/AGENTS/src/tests/docs/scripts/assets/work/outputs/progress）、命名约定、文档导航（指向 references/documents.md）、临时内容与进度规则、收尾清单。无 TODO/截断。
- **支撑文件**：`references/documents.md` 存在（72 行），内容完整且与正文的职责划分（progress 归档属 handoff、本技能不另建交接文件）一致。
- **过时/失效**：无；正文与 workspace AGENTS.md 的 progress 约定互相吻合。
- **评价**：**可用**。

## 11. python-helper

- **frontmatter**：`name` 一致；description "Python idioms, packaging and debugging snippets"——**承诺提供 snippets**。模型可见，会话目录在列。
- **正文完整性**：**不完整——正文明确写有 "Placeholder content: replace with your real skill."** 全文 19 行：三行 When to use（venv/uv/pip 选择、打包问题、读 traceback）加两条 Notes，没有任何 idioms、packaging 或 debugging 的实质内容，与 description 承诺名实不符。
- **支撑文件**：`configs/common.yaml` 存在且确实列有 python-helper（"Enabled for every environment" 属实）；无其它文件引用。
- **过时/失效**：无失效引用；问题是内容本身为占位。
- **评价**：**基本可用有小问题**——结构完好、配置接线正确，但正文自认占位；作为示例技能成立，作为实际可用的 python-helper 不成立。

## 12. setup-matt-pocock-skills

- **frontmatter**：`name` 一致；description 清楚（一次性配置 issue tracker、triage 标签、领域文档布局，先于其它工程技能运行）；`disable-model-invocation: true`。
- **正文完整性**：完整。五步流程（Explore→Present→Confirm→Write→Done）、探索清单（git remote、AGENTS/CLAUDE.md、CONTEXT.md、docs/adr、docs/agents、.scratch、triage 是否安装、monorepo 信号）、三个 Section 的推荐答案、`## Agent skills` 块模板。无 TODO/截断。
- **支撑文件**：5 个种子模板**全部存在**——`issue-tracker-github.md`、`issue-tracker-gitlab.md`、`issue-tracker-local.md`、`triage-labels.md`、`domain.md`；三个 issue-tracker 模板均含 wayfinder 所需的 "Wayfinding operations" 节（与 wayfinder 的交叉引用验证通过）；`triage-labels.md` 五个规范角色与 SKILL.md 列出的默认标签一致；正文前提"triage 技能是否安装"——triage 技能存在于本仓库。
- **过时/失效**：GitHub 路线依赖 `gh` CLI 与较新的 sub-issues / native issue dependencies 特性，模板已写明 fallback（Blocked by 行约定）；本机无 `gh`，但该技能是探索式流程，会依 git remote 实况引导到 GitHub/GitLab/本地 markdown，不构成内容失效。
- **评价**：**可用**。

## 13. teach

- **frontmatter**：`name` 一致；description "Teach the user a new skill or concept, within this workspace" 够用；`argument-hint` 与 `disable-model-invocation: true` 齐备。
- **正文完整性**：完整（140 行）。教学工作区文件布局（MISSION.md、reference/、RESOURCES.md、learning-records/、lessons/、assets/、NOTES.md）、教学哲学（知识/技能/智慧）、Fluency vs Storage Strength、课程规范（HTML、Tufte 风格、编号、引用一手来源）、Assets 复用、Mission、ZPD、NOTES.md。无 TODO/截断。
- **支撑文件**：正文链接的 3 个格式文件全部存在——`MISSION-FORMAT.md`、`RESOURCES-FORMAT.md`、`LEARNING-RECORD-FORMAT.md`。**问题：目录中的 `GLOSSARY-FORMAT.md` 存在但正文从未引用**（正文只泛泛说 "Glossaries, in particular, are an essential reference"，未链接该文件；而 `LEARNING-RECORD-FORMAT.md` 内部以 `[[GLOSSARY.md]]` 呼应它）——孤儿支撑文件，glossary 格式约定缺少入口。
- **过时/失效**：无。
- **评价**：**基本可用有小问题**——教学主流程完整可用，但 GLOSSARY-FORMAT.md 未接线，按正文走会漏掉 glossary 格式约定。

## 14. wait-what

- **frontmatter**：`name` 一致；description 简短明确（"Stop. That last message did not land — re-pitch it."）；`disable-model-invocation: true`。
- **正文完整性**：正文一段（重新表述要求：补上下文、用 ASD-STE100 简明技术英语、用 `CONTEXT.md` 的统一语言）——一行体是刻意的轻量纠正指令，完整非截断。
- **支撑文件**：无本地文件引用；`CONTEXT.md` 是 grill-with-docs/domain-modeling 体系的项目产物，ask-matt 中有说明其来源，依赖关系成立。
- **过时/失效**：无。ASD-STE100 为真实存在的规范。
- **评价**：**可用**。

## 15. wayfinder

- **frontmatter**：`name` 一致；description 详尽（把超大工作规划为 issue tracker 上的共享决策地图）；`disable-model-invocation: true`。
- **正文完整性**：完整（128 行）。Plan-don't-do 原则、Refer by name、地图结构（map issue + 模板 + 子票）、票据类型（research/prototype/grilling/task，HITL/AFK 划分）、fog of war、out of scope、两种调用模式（Chart/Work through，每次会话至多解决一票、research 票例外）。无 TODO/截断。
- **支撑文件**：无本地文件引用；引用的技能 `/setup-matt-pocock-skills`、`/research`、`/prototype`、`/grilling`、`/domain-modeling` 全部存在；正文要求 tracker 文档含 "Wayfinding operations" 节——已在 setup 技能的三个 issue-tracker 模板中核实存在。
- **过时/失效**：无。无 tracker 时默认 local-markdown 的回退使本机（无 gh/glab）仍可运行。
- **评价**：**可用**。

## 16. wizard

- **frontmatter**：`name` 一致；description 详尽且含正反触发（何时用/何时不用——"Don't invoke this for steps the agent can perform itself"）；模型可见，会话目录在列。
- **正文完整性**：完整。四步流程（Scope→Map journey→Author→Verify and hand off），每步有 Done when 判据，"never invent steps that may not exist" 等防幻觉约束明确。无 TODO/截断。
- **支撑文件**：`template.sh` 存在（204 行），正文列举的库助手**逐一核对全部在模板中实现**：`stage`、`say`/`step`（另有 note/warn/banner/finish）、`open_url`（wslview/explorer.exe/xdg-open/open 跨平台回退）、`ask`/`ask_secret`、`write_env`（幂等 upsert）、`set_secret`/`set_var`、`pause`/`confirm`、`TOTAL_STAGES` 与 STAGES 标记；`set -euo pipefail` 合规。
- **过时/失效**：无。gh 缺失时模板优雅降级（记录进 SKIPPED 收尾清单）；shellcheck 用 "if available" 措辞；对 `bash -n` 静态校验的要求合理。
- **评价**：**可用**。

## 17. writing-for-agents

- **frontmatter**：`name` 一致；description 清楚（创建/编辑技能或 AGENTS.md/CLAUDE.md 时使用）；模型可见，会话目录在列。
- **正文完整性**：完整（81 行）。Context pointers（措辞决定触发）、两种负载（context load / cognitive load）、信息层级三级阶梯与 progressive disclosure、co-location、sprawl、步骤与完成标准（clarity/demand、premature completion）、拆分时机、leading words（含 negation 失败模式）、剪枝纪律（单一事实源、环境即事实源、relevance、no-ops）。无 TODO/截断。
- **支撑文件**：`SKILL-MECHANICS.md` 存在（22 行），与正文两处互链一致，内容（model-invoked vs user-invoked 的取舍与 router skills）自洽。
- **过时/失效**：无。
- **评价**：**可用**。

---

## 问题清单

| 技能 | 问题 | 严重程度 | 建议 |
| --- | --- | --- | --- |
| agent-reach | 本机 PATH 缺少 `agent-reach`/`mcporter`/`opencli`/`bili`/`twitter`/`rdt`/`yt-dlp`/`gh` 等依赖 CLI，多数平台路由命令无法执行，连 `doctor --json` 自检也无法运行 | 中（环境依赖，非内容缺陷） | 在使用该技能的机器上按其 docs/install.md 装配后端；或在技能/装配层显式标注"仅限已装配后端的环境" |
| python-helper | 正文自述 "Placeholder content: replace with your real skill"，无任何实质 snippets，与 description 的承诺名实不符 | 中 | 补写真实内容；或把 description 改为与 game-dev/image-tools 一致的示例技能定位 |
| teach | `GLOSSARY-FORMAT.md` 存在于技能目录但 SKILL.md 从未引用（孤儿支撑文件，glossary 格式约定缺入口） | 低 | 在正文 Glossaries 相关段落补一行链接 `[GLOSSARY-FORMAT.md](./GLOSSARY-FORMAT.md)` |
| agent-reach | frontmatter 使用非标准字段 `triggers`（嵌套映射）与 `metadata.openclaw`，部分 harness 会忽略 | 低 | 无需修改；跨 harness 迁移时注意这些字段不被解析 |
| game-dev、image-tools | description 触发信息弱（仅一句 "Personal-only ... helpers"），且无 `agents/openai.yaml`；会话技能目录不可见 | 低 | 若仅作示例可保留现状；若要真实启用，需补 description 触发词并核实环境装配 |
| ask-matt（含 PHASE-BOUNDARIES.md） | `/clear`、`/compact` 为 Claude Code 类 harness 命令，在其它 harness 中语义或可用性不同 | 低 | 可选：加一句"命令名随 harness 而异"的中立提示 |
| setup-matt-pocock-skills | GitHub 路线依赖 `gh` CLI 与 sub-issues/native dependencies 较新特性，本机无 `gh` | 低（模板已含 fallback，有本地 markdown 回退） | 保持现状 |
| wizard | 依赖 `gh` 写 GitHub secrets，本机 `gh` 缺失时仅能写 `.env` | 低（template.sh 已优雅降级并记录 SKIPPED） | 保持现状 |
| ask-matt、grill-me、grill-with-docs、handoff、setup-matt-pocock-skills、teach、wait-what、wayfinder | 均带 `disable-model-invocation: true`，不出现在会话模型可见技能目录——设计使然（用户手动调用），非缺陷 | 信息 | 无需修改；记录为会话可见性差异的解释项 |
