# 开发流程类技能深度审计（t6）

- 审计人：content-devflow（任务 t6，attempt 1）
- 审计日期：2026-02-27
- 审计对象：`D:\App\agent-workspace\skills\` 下 15 个开发流程类技能（逐个完整读取 SKILL.md 正文 + 全部支撑文件核对）
- 审计方式：纯只读静态检查。逐行读取 SKILL.md 全文（含正文），逐个核对正文引用的相对路径/绝对路径/技能名是否真实存在；未运行任何技能或脚本。
- 唯一写入文件：本报告 `skill-audit/cat-devflow.md`。未修改任何技能内容，未触碰 `dist\`。

## 结论总览

| 技能 | name 一致 | description 触发场景 | 正文完整可执行 | 支撑文件引用 | 会话可见 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| code-review | ✓ | 弱（无"何时用"表述） | ✓ 但为自声明占位 | configs/common.yaml 存在 ✓ | 可见 | 基本可用（占位骨架） |
| tdd | ✓ | ✓ 清晰 | ✓ 完整 | tests.md / mocking.md / /codebase-design / code-review 均存在 ✓ | 可见 | 可用 |
| git-delivery | ✓ | ✓ 清晰（中文） | ✓ 完整 | 无文件引用；agentctl 存在 ✓ | 可见 | 可用（含机器特定注记） |
| git-helper | ✓ | 弱 | ✓ 但为自声明占位 + 测试痕迹 | configs/common.yaml 存在 ✓ | 可见 | 基本可用（占位骨架） |
| diagnosing-bugs | ✓ | ✓ 清晰 | ✓ 完整（140 行，六阶段） | scripts/hitl-loop.template.sh 存在 ✓；/improve-codebase-architecture 存在 ✓ | 可见 | 可用 |
| resolving-merge-conflicts | ✓ | ✓ 清晰 | ✓ 完整（精简但自洽） | 无文件引用 | 可见 | 可用 |
| implement | ✓ | 一般（一句话说明用途） | ✓ 完整（极简） | /tdd、/code-review 存在 ✓ | 隐藏 | 可用 |
| improve-codebase-architecture | ✓ | ✓ 清晰 | ✓ 完整 | HTML-REPORT.md 存在 ✓；/codebase-design、/grilling、/domain-modeling 存在 ✓ | 隐藏 | 可用 |
| triage | ✓ | ✓ 清晰 | ✓ 完整（112 行） | AGENT-BRIEF.md、OUT-OF-SCOPE.md 存在 ✓；/grilling、/domain-modeling、/setup-matt-pocock-skills 存在 ✓ | 隐藏 | 可用（需先跑 setup 配置） |
| run-tickets | ✓ | ✓ 清晰（含显式调用约束） | ✓ 完整（100 行） | references/github-tracker.md、local-tracker.md、scripts/ticket_graph.py 存在 ✓；docs/agents/issue-tracker.md **不存在** | 隐藏 | 基本可用（有小问题） |
| to-spec | ✓ | ✓ 清晰 | ✓ 完整（含完整模板） | /setup-matt-pocock-skills 存在 ✓ | 隐藏 | 可用（需先跑 setup 配置） |
| to-tickets | ✓ | ✓ 清晰 | ✓ 完整（含双模板） | /setup-matt-pocock-skills 存在 ✓ | 隐藏 | 可用（需先跑 setup 配置） |
| to-questionnaire | ✓ | ✓ 清晰 | ✓ 完整（含模板） | 无文件引用 | 隐藏 | 可用 |
| define-bounded-goal | ✓ | ✓ 清晰 | ✓ 完整（208 行） | 引用 get_goal/create_goal 工具；**token_budget 参数与当前 Goal 工具签名不符** | 可见 | 基本可用（有小问题） |
| prototype | ✓ | ✓ 清晰 | ✓ 完整 | LOGIC.md、UI.md 存在 ✓ | 可见 | 可用 |

**总体**：15 个技能无一处目录名/frontmatter name 不一致；无截断正文；支撑文件除 1 个条件外全部真实存在。主要问题集中在：两个 MVP 占位示例技能（code-review、git-helper）、run-tickets 的两处路径/配置耦合、define-bounded-goal 与当前 Goal 工具签名的参数漂移。

---

## 逐技能检查

### 1. code-review（`skills/code-review\SKILL.md`，25 行）

- **frontmatter**：`name: code-review` 与目录一致；`description: Structured code review - correctness, style, and tests.` 存在，但只是主题标签，未说明触发场景（无 "use when" 类表述）。
- **正文完整性**：结构完整（When to use / Checklist / Notes），无截断；但 L8 自述 "Example skill shipped with the agent-workspace MVP."、L24 自述 "Placeholder content: replace with your real skill." —— **自我声明的占位示例**。实质内容仅 4 条通用审查清单（正确性/边界/测试/风格）。
- **引用核对**：L25 引用 `configs/common.yaml` —— 已验证存在（`configs\common.yaml`）。
- **过时/失效内容**：无失效命令或路径；问题在于内容深度而非失效。
- **交叉影响**：tdd（L38）与 implement（L13）将 `/code-review` 作为收尾审查环节引用——引用本身有效，但被引用方是占位骨架，实际引导力弱。
- **一句话结论**：基本可用（有小问题）——frontmatter 正常、能跑通，但正文是官方留的占位示例，仅 4 条清单，深度远低于会话目录描述给人的预期。

### 2. tdd（`skills/tdd\SKILL.md`，38 行）

- **frontmatter**：name 一致；description 明确触发场景（test-first、red-green-refactor、integration tests）。
- **正文完整性**：完整。好测试标准、seam 概念、反模式（implementation-coupled / tautological / horizontal slicing）、循环规则（red before green、vertical slice、重构不属于循环）均成文，无 TODO/占位/截断。
- **引用核对**：
  - `tests.md`、`mocking.md` —— 存在且为完整真实内容（77/59 行，含好/坏测试与 mock 边界示例；示例为 TypeScript/jest 风格）。
  - `/codebase-design` 技能 —— 存在于本工作区。
  - `code-review` 技能 —— 存在（内容为占位，见上）。
  - `CONTEXT.md`、ADR —— 文中均为条件引用（"if it exists"），合法。
- **过时/失效内容**：无。
- **一句话结论**：可用 —— 指令完整自洽，所有支撑文件与技能交叉引用真实有效。

### 3. git-delivery（`skills/git-delivery\SKILL.md`，57 行）

- **frontmatter**：name 一致；中文 description 明确触发场景（修改任务收尾，不用于只读分析/审查）。
- **正文完整性**：完整。任务边界、按影响范围验证矩阵、暂存与提交规范（Conventional Commits 细则）、推送授权、完成报告六节成文，无占位/截断。
- **引用核对**：无支撑文件引用；L52 提及 `agentctl update` —— 工作区 `agentctl/` 存在（AGENTS.md 确认其为本工作区 Python CLI）。
- **过时/失效内容**：无失效引用。**注意**：L52 内嵌了本机安全组件按第二参数精确拦截 `git push` 的症状描述与绕行方案（`git -c alias.push= push`），并注明"用户终端是否同样受影响未验证"。这是机器特定运维知识固化进技能正文，属设计意图（作者实测记录），非缺陷；但跨机器复用该技能时该段不适用，需复核。
- **一句话结论**：可用 —— 指令完整可执行；内嵌的 push 拦截绕行注记为机器特定知识，换环境使用时需自行判断是否仍适用。

### 4. git-helper（`skills/git-helper\SKILL.md`，22 行）

- **frontmatter**：name 一致；`description: Everyday git helpers - branch hygiene, commit messages, safe undo.` 存在但触发场景表述弱（与 code-review 同款问题）。
- **正文完整性**：结构完整无截断；但 L8 "Example skill shipped with the agent-workspace MVP."、L18 "Placeholder content: replace with your real skill." —— **自声明占位示例**。实质内容仅 3 条使用场景 + 1 条建议。
- **引用核对**：L19 引用 `configs/common.yaml` —— 存在。
- **过时/失效内容**：L20 有遗留测试痕迹标题 `## Update note (simulated edit on personal machine)`（其下内容本身无害：建议用 `git switch -c`），暴露该文件曾被用作编辑功能冒烟测试，未清理。
- **一句话结论**：基本可用（有小问题）——占位示例 + 残留测试痕迹标题，内容深度不足。

### 5. diagnosing-bugs（`skills/diagnosing-bugs\SKILL.md`，140 行）

- **frontmatter**：name 一致；description 明确触发场景（"diagnose"/"debug this"、报错/变慢）。
- **正文完整性**：完整且质量高。Redact（脱敏）要求、六阶段流程（反馈回路 → 复现最小化 → 假设 → 插桩 → 修复+回归测试 → 清理复盘）、10 种构造反馈回路的方法、完成判据 checkbox、非确定性 bug 处理，全部成文，无占位/截断。
- **引用核对**：
  - `scripts/hitl-loop.template.sh` —— 存在，44 行完整 bash 模板（step/capture 两个辅助函数，带编辑标记区，`set -euo pipefail`）。
  - `/improve-codebase-architecture` 技能 —— 存在于本工作区。
  - `CONTEXT.md`、ADR —— 条件引用，合法。
  - 工具名（Playwright/Puppeteer、`git bisect run`、`performance.now()`）—— 均为通用真实工具。
- **过时/失效内容**：无。
- **一句话结论**：可用 —— 正文完整、自洽、可执行，支撑脚本真实。

### 6. resolving-merge-conflicts（`skills/resolving-merge-conflicts\SKILL.md`，14 行）

- **frontmatter**：name 一致；description 明确触发场景（进行中的 merge/rebase 冲突）。
- **正文完整性**：完整。5 步流程（看状态 → 找双方原始意图 → 逐 hunk 解决（绝不 `--abort`）→ 跑自动化检查 → 完成 merge/rebase）自洽可执行，无占位/截断。
- **引用核对**：无支撑文件引用。
- **过时/失效内容**：无。
- **一句话结论**：可用 —— 精简但完整，指令可直接执行。（附注：15 个技能中 11 个带 `agents/openai.yaml` 元数据文件，此技能与 code-review、git-delivery、git-helper、triage 一样没有；SKILL.md 正文未引用该文件，不构成缺陷，仅记录分布。）

### 7. implement（`skills/implement\SKILL.md`，15 行）

- **frontmatter**：name 一致；description 一句话说明用途（按 spec/tickets 实现），触发场景表述一般但可理解；带 `disable-model-invocation: true`。
- **正文完整性**：完整。5 条指令（实现 → 尽量用 /tdd → 定期类型检查/单测 → 收尾跑全量 → /code-review → 提交）自洽，无占位/截断。极简是有意设计（编排型技能，细节委托给被引用技能）。
- **引用核对**：`/tdd`、`/code-review` 均存在于本工作区（后者为占位骨架，见第 1 节）。
- **过时/失效内容**：无。
- **一句话结论**：可用 —— 极简编排技能，引用链完整；其实际效果部分受 code-review 占位状态影响。

### 8. improve-codebase-architecture（`skills/improve-codebase-architecture\SKILL.md`，71 行）

- **frontmatter**：name 一致；description 清晰（扫描 deepening 机会 → HTML 报告 → grilling）；带 `disable-model-invocation: true`。
- **正文完整性**：完整。三阶段流程（Explore → HTML 报告 → Grilling loop）细节充分：热点定位方法、候选卡片字段、报告落盘路径（$TMPDIR / %TEMP%）、打开方式（xdg-open/open/start）、ADR 冲突处理、/domain-modeling 联动，无占位/截断。
- **引用核对**：
  - `HTML-REPORT.md` —— 存在，123 行完整（Tailwind/Mermaid CDN 脚手架、6 种图式、风格与词汇约束）。
  - `/codebase-design`、`/grilling`、`/domain-modeling` —— 均存在于本工作区。
  - `CONTEXT.md`、`docs/adr/` —— 条件引用（"if it doesn't exist, create lazily"），合法。
- **过时/失效内容**：无。Tailwind CDN、Mermaid 11 ESM CDN、三种 OS 打开命令均现行有效。
- **一句话结论**：可用 —— 正文与支撑文档完整配套，跨技能引用全部有效。

### 9. triage（`skills/triage\SKILL.md`，112 行）

- **frontmatter**：name 一致；description 清晰（triage 角色状态机）；带 `disable-model-invocation: true`。
- **正文完整性**：完整。角色模型（2 类目 + 5 状态）、AI 免责声明强制前缀、show-attention 三桶、逐 issue 流程（收集 → 建议 → 验证 → grilling → 落标签/评论/关闭）、needs-info 模板、恢复会话，无占位/截断。
- **引用核对**：
  - `AGENT-BRIEF.md` —— 存在，207 行完整（brief 原则与模板）。
  - `OUT-OF-SCOPE.md` —— 存在，105 行完整（`.out-of-scope/` KB 目录约定与文件格式）。
  - `/grilling`、`/domain-modeling`、`/setup-matt-pocock-skills` —— 均存在于本工作区。
  - "issue-tracker config"（L11）与标签映射（L43）—— 依赖一次性 `/setup-matt-pocock-skills` 写入的仓库配置；**本工作区 `docs/` 目录不存在**，即从未配置过。技能自身提供了兜底指引（"should have been provided to you - run /setup-matt-pocock-skills if not"），属可恢复状态而非失效。
- **过时/失效内容**：无。
- **一句话结论**：可用 —— 正文完整、支撑文档真实；首次在本工作区实际使用前需运行 `/setup-matt-pocock-skills` 生成 tracker/标签配置。

### 10. run-tickets（`skills/run-tickets\SKILL.md`，100 行）

- **frontmatter**：name 一致；description 清晰且带显式调用约束（"Use only when the user explicitly invokes /run-tickets and authorizes..."）；带 `disable-model-invocation: true`。
- **正文完整性**：完整且详尽。输入解析（本地 issues/ 目录或 GitHub 父 issue）、能力检查（multi-agent + worktree）、preflight 7 步、rolling 调度器 7 步、worker 合同（含心跳格式与返回格式）、集成与恢复、进度汇报，无占位/截断。
- **引用核对**：
  - `references/github-tracker.md`（29 行）、`references/local-tracker.md`（36 行）—— 均存在且完整。
  - `scripts/ticket_graph.py` —— 工作区副本存在，147 行完整（解析 `# NN — title` / `**Blocked by:**` / `**Status:**`，查重/自依赖/环检测/frontier 输出，`--format json` 与 SKILL.md 用法一致）。同时按 Test-Path 验证，`C:\Users\E0465\.agents\skills\run-tickets\scripts\ticket_graph.py` **当前也存在**，故 L27 的硬编码命令在本机可解析。
  - `docs/agents/issue-tracker.md`（L18，**无条件引用**）—— **本工作区不存在**（无 `docs/` 目录）。其引用文档 github-tracker.md 内部对同类文件（`docs/agents/triage-labels.md`）用的是 "when present" 条件引用并可兜底，SKILL.md 正文这一处没有兜底措辞。
  - 被引用技能 `to-tickets`、`implement`、`tdd`、`code-review` —— 均存在。
- **过时/失效内容**：
  - L27 helper 调用硬编码绝对路径 `$env:USERPROFILE\.agents\skills\run-tickets\scripts\ticket_graph.py`：本机当前有效，但与工作区 `skills\run-tickets\scripts\` 副本**双份并存**，存在漂移风险；且该路径假设技能安装在 `~\.agents\skills`，换安装位置即失效。
  - GitHub 模式在本工作区因 `docs/agents/issue-tracker.md` 缺失而未完成配置（setup 技能未运行过）。
- **一句话结论**：基本可用（有小问题）——本地模式当前可跑通；GitHub 模式无条件引用的 tracker 配置在本工作区缺失，helper 路径硬编码形成双副本漂移与安装位置耦合。

### 11. to-spec（`skills/to-spec\SKILL.md`，75 行）

- **frontmatter**：name 一致；description 清晰（把当前对话合成 spec 发布到 tracker，明确"不采访"）；带 `disable-model-invocation: true`。
- **正文完整性**：完整。三步流程（探索 → 议定 seam → 按 spec-template 写并发布、打 `ready-for-agent` 标签）+ 完整内嵌 spec 模板（Problem/Solution/User Stories/Implementation Decisions/Testing Decisions/Out of Scope/Further Notes），含原型片段例外规则，无占位/截断。
- **引用核对**：`/setup-matt-pocock-skills` 存在（本工作区未运行过，见 triage 一节；技能自带兜底指引）。无其他文件引用。
- **过时/失效内容**：无。
- **一句话结论**：可用 —— 正文完整自洽；发布目标 tracker 需先经 setup 配置，缺失时有明确兜底。

### 12. to-tickets（`skills/to-tickets\SKILL.md`，105 行）

- **frontmatter**：name 一致；description 清晰（拆 tracer-bullet tickets + 阻塞边，双 tracker 形态）；带 `disable-model-invocation: true`。
- **正文完整性**：完整。五步流程（收集 → 探索 → 起草垂直切片（含 wide refactor 的 expand–contract 例外）→ 用户确认 → 发布）+ 本地 per-ticket 模板与 issue 模板双模板，无占位/截断。
- **引用核对**：`/setup-matt-pocock-skills` 存在（同上，未配置但有兜底）。本地发布路径 `.scratch/<feature-slug>/issues/` 为运行时约定，非引用。
- **过时/失效内容**：无。
- **一句话结论**：可用 —— 正文完整、模板齐备；同 to-spec 依赖一次性 setup 配置，有兜底指引。

### 13. to-questionnaire（`skills/to-questionnaire\SKILL.md`，53 行）

- **frontmatter**：name 一致；description 清晰（把答不了的问题变成给他人填的问卷）；带 `disable-model-invocation: true`。
- **正文完整性**：完整。三步（问收件人 → 问要回来的东西 → 写文件）+ 完整内嵌问卷模板（Purpose/From-To/Context/How to answer/主题分节/Anything else）+ 单问一意、答案留白、"why this matters" 规则，无占位/截断。
- **引用核对**：无文件引用；产出文件 `to-questionnaire-<slug>.md` 为运行时产物。
- **过时/失效内容**：无。
- **一句话结论**：可用 —— 自包含完整，无外部依赖。

### 14. define-bounded-goal（`skills/define-bounded-goal\SKILL.md`，208 行）

- **frontmatter**：name 一致；description 清晰（可测量目标 + 时间盒 + 预算契约 + 结构化交接）。无 `disable-model-invocation`；但 `agents/openai.yaml` 设 `allow_implicit_invocation: false`（仅 Codex 侧生效，DSH 会话技能目录不读该字段），且正文 L14 自我限定 "Use this skill only when the user explicitly invokes `$define-bounded-goal`" —— 三层约束之间存在轻微不一致（见问题表）。
- **正文完整性**：完整且质量高。工作流 8 步、Budget Contract 字段表与默认值、depth→verification 映射、时间预算→深度建议表、8 个固定 stop_reason、Goal 质量条（Good/Weak 示例）、结构化交接格式，无占位/截断。
- **引用核对**：
  - `get_goal`、`create_goal` —— 当前运行环境（DSH harness）确实提供这两个 Goal 工具。
  - **`token_budget`（L60："Pass `token_budget` only when the user explicitly supplied a token count"）—— 当前 `create_goal` 工具签名仅接受 `objective` / `max_goal_rounds`，没有 token_budget 参数**。L134 停止原因 `token_budget_exhausted`（"Goal tooling reports the token budget exhausted"）同理依赖一个当前工具不报告的维度。这是从 OpenAI 源技能（正文 L12 自述 derived from OpenAI's curated `define-goal` skill）继承的参数漂移：不影响目标定义主流程，但按文执行会尝试传递不存在的参数。
- **过时/失效内容**：即上述 token 维度漂移；其余（时间盒、stop_reason、交接格式）与当前环境自洽。
- **一句话结论**：基本可用（有小问题）—— 目标定义与预算契约主体完全可用；token_budget 相关两处引用了当前 Goal 工具不存在的参数/信号，需按当前环境理解或修订。

### 15. prototype（`skills/prototype\SKILL.md`，26 行）

- **frontmatter**：name 一致；description 清确触发场景（sanity-check 状态模型/逻辑，或探索 UI）。
- **正文完整性**：完整。分支选择（LOGIC vs UI，含歧义兜底）+ 6 条通用规则（一次性标记、一键可跑、默认无持久化、跳过打磨、暴露状态、完成后归档到 throwaway 分支），无占位/截断。
- **引用核对**：`LOGIC.md`（67 行）、`UI.md`（112 行）—— 均存在且为完整真实内容（logic：纯 reducer/状态机模块 + 单 HTML 交付；UI：?variant= 切换 + 浮动底栏 + 两个 sub-shape）。
- **过时/失效内容**：无。
- **一句话结论**：可用 —— 入口清晰、分支文档完整配套。

---

## 会话可见性一致性（附注）

以本会话（DSH harness）的 available_skills 目录核对 15 个技能：

- **模型可见（8 个）**：code-review、tdd、git-delivery、git-helper、diagnosing-bugs、resolving-merge-conflicts、define-bounded-goal、prototype —— 均无 `disable-model-invocation` 标记，目录中 description 与 frontmatter description 逐字一致。
- **模型不可见（7 个）**：implement、improve-codebase-architecture、triage、run-tickets、to-spec、to-tickets、to-questionnaire —— **全部**带 `disable-model-invocation: true`，与目录缺失状态 100% 对应。

即 `disable-model-invocation` 机制在当前会话生效且双向一致；15 个技能中无"标记了隐藏但仍可见"或"未标记却不可见"的错位。

## 问题清单

| 技能 | 问题 | 严重程度 | 建议 |
| --- | --- | --- | --- |
| code-review | 正文为自声明占位示例（L8/L24），实质仅 4 条通用清单；description 未写触发场景，与会话目录给人的预期不匹配 | 中 | 按项目实际审查流程扩写正文；或至少在 description 中明确当前为骨架示例 |
| git-helper | 正文为自声明占位示例（L18）；残留测试痕迹标题 "Update note (simulated edit on personal machine)"（L20）；description 触发场景弱 | 中 | 扩写真实内容，删除测试痕迹标题；同步改写 description |
| run-tickets | L18 对 `docs/agents/issue-tracker.md` 为无条件引用，本工作区无 `docs/` 目录（GitHub 模式配置缺失）；同文件内其他同类引用均为条件式可兜底 | 中 | 将该句改为条件引用（"if present, … otherwise run /setup-matt-pocock-skills"），与 github-tracker.md 的措辞对齐 |
| run-tickets | L27 helper 调用硬编码 `$env:USERPROFILE\.agents\skills\...` 绝对路径：本机当前可解析，但与工作区 `skills\run-tickets\scripts\` 副本双份并存（漂移风险），且换安装位置即失效 | 中 | 改为相对 SKILL.md 自身位置解析的路径，或在正文中注明"工作区与 ~/.agents 两副本需保持同步" |
| define-bounded-goal | L60 的 `token_budget` 参数与 L134 的 `token_budget_exhausted` 停止原因，在当前 Goal 工具（`create_goal` 仅 objective/max_goal_rounds）中不存在，属 OpenAI 源技能参数漂移 | 低 | 删除或改写为当前工具实际支持的参数（如 max_goal_rounds）；至少加注"当前环境不适用" |
| define-bounded-goal | 正文限定"仅显式 $ 调用"（L14）+ openai.yaml `allow_implicit_invocation: false`，但 frontmatter 无 `disable-model-invocation`，DSH 会话目录按 description 可自动触发 | 低 | 补 `disable-model-invocation: true`（与其余 7 个工程技能对齐），或在 description 中写入显式调用要求 |
| triage / to-spec / to-tickets / run-tickets | 共同依赖一次性 `/setup-matt-pocock-skills` 写入的仓库配置（tracker + 标签映射）；本工作区从未配置。前三者有兜底指引，run-tickets 无（见上行） | 低 | 首次实际使用前运行 `/setup-matt-pocock-skills`；无需改技能文本 |
| git-delivery | L52 内嵌本机安全组件拦截 `git push` 的症状与 workaround（`git -c alias.push= push`），属机器特定运维知识，跨机器复用不适用 | 低 | 保留但在句首加"本机环境注记"标记；安全组件变化时复核更新 |
| tdd / implement | 引用 `code-review` 作为收尾审查环节；被引用技能目前为占位骨架，引用链有效但引导深度不足 | 低 | 随 code-review 扩写自动改善，无需改这两个技能 |

## 审计局限

- 纯静态只读检查：未运行任何技能、脚本（含 ticket_graph.py）或 Git 命令，"可执行"判断基于文本完整性与引用真实性。
- `~\.agents\skills`、`~\.codex\skills` 两处的存在性/内容比对不属于本任务范围（由其他任务负责）；本报告仅用 Test-Path 验证了 run-tickets 硬编码路径在本机存在这一事实。
- git-delivery L52 所述安全组件行为无法静态验证，按作者自述记录处理。
