# 分类深读审计：设计 / UI / 文档 / 知识类技能（t7）

- 审计对象：`D:\App\agent-workspace\skills\` 下 10 个技能
- 审计方式：逐个完整读取 SKILL.md 正文（非仅 frontmatter），逐个核对正文中引用的支撑文件相对路径；对 JSON 资源做解析验证，对 CSV 数据行数与 description 声称的数量逐项比对；对 stub 技能引用的外部配置（configs/*.yaml、.env.example、agentctl 子命令）在仓库根目录逐一验证。
- 只读审计：除本文件外未写入任何文件；未修改任何技能内容。

## 结论速览

| 技能 | 评价 |
|---|---|
| qt-ui-design | 可用 |
| pyside6-fluent-ui | 可用（2 处低危卫生/说明类小问题） |
| ui-ux-pro-max | 可用（2 处低-中危：README 缺失、调用路径模板） |
| document-helper | 不可用（空壳示例，无实际指令） |
| internal-doc-search | 不可用（空壳示例，无实际指令） |
| jira-helper | 不可用（空壳示例，无实际指令） |
| onenote | 基本可用（正文完整，但运行依赖的 OneNote MCP 本机未检出） |
| research | 可用 |
| domain-modeling | 可用 |
| codebase-design | 可用 |

---

## 1. qt-ui-design

**文件**：SKILL.md（333 行）、README.md、LICENSE.txt；无 scripts/references 目录。

- **frontmatter**：`name: qt-ui-design` 与目录名一致；description 完整说明触发场景（Qt/QML、web、嵌入式 MPU/MCU 的 UI 设计或审计）✓；额外带 license/compatibility/metadata 字段，格式合法。
- **正文完整性**：333 行完整自洽——7 项 intake 询问、设计原则、模块化字阶（含 worked example 与 QML/CMake 代码）、多输入与键盘导航、语义色、本地化/RTL、WCAG 2.2 检查、AI UX、嵌入式 MCU 专章（覆盖软件光栅化约束表、布局、交互、字阶、安全）、审计分级、参考链接。无 TODO/占位符/截断。
- **支撑文件**：正文仅引用外部 URL（NN/g、lawsofux、WCAG 2.2、modularscale、Qt 文档等），不依赖本地支撑文件。README 的 Files 表只列 SKILL.md（LICENSE.txt 未列出，属于文档小瑕疵，info 级）。
- **过时/失效内容**：未发现。Qt 6.7+（iOS/FluentWinUI3 样式）、Qt 6.x API 均为现行内容；外部链接域名均真实。
- **评价**：**可用**——自包含概念型技能，正文质量高，无外部依赖。

## 2. pyside6-fluent-ui

**文件**：SKILL.md（319 行）、references/ 13 个 md、resources/ 5 个 json + 1 个 md、scripts/ 6 个、templates/pyside6_fluent_ui/ 18 个源码文件、tests/ 7 个、examples/、agents/openai.yaml、VERSION（0.7.0-rc.1）、SHA256SUMS、NOTICE.md、LICENSE。

- **frontmatter**：`name: pyside6-fluent-ui` 与目录名一致；description 详细说明触发场景（构建/审计/渐进重构 PySide6 Widgets 界面、工作台壳、主题系统、无障碍审查），并明确反模式边界 ✓。
- **正文完整性**：319 行完整——scope、authority order、6 种 operating modes、15 条不可协商规则、9 步工作流、主题架构分工表、Activity/Status/Title Bar 三个契约、无障碍基线、输出期望与完成门槛。无 TODO/占位符/截断。
- **支撑文件逐项核对**（全部通过）：
  - 正文"Load only the references needed"表列出的 13 个 references/*.md 全部存在（fluent-principles / token-architecture / qt-styling-architecture / component-mappings / interaction-states / accessibility / workbench-shell / activity-bar / status-bar / title-bar / refactor-playbook / validation-checklist / anti-patterns）。
  - resources/qt-token-map.json、shell-token-map.json、component-state-matrix.json、fluent2-official-web-theme-tokens.json、source-manifest.json 全部存在且 **JSON 解析有效**（pwsh ConvertFrom-Json 逐个验证）。
  - 正文点名的类 `FluentThemeManager`、`FluentWindowFrameController`、`WindowsSnapLayoutWindowMixin`、`WindowsSnapLayoutAdapter`、`DWMWA_BORDER_COLOR` 均在 templates/pyside6_fluent_ui/theme.py、window_frame.py、windows_title_bar.py 中实际定义；references/title-bar.md 引用的 templates/pyside6_fluent_ui/title_bar.py、window_frame.py、windows_title_bar.py 均存在。
  - scripts/（audit_qt_styles.py、check_contrast.py、run_checks.sh、update_checksums.py、validate_skill.py、verify_windows_snap_layout.py）与 examples/widget_gallery.py 均存在。
- **问题**：
  - tests/ 与 scripts/ 下残留 `__pycache__/*.pyc`（含 8 个 pyc 文件），打包/同步卫生问题（低危）。
  - `scripts/run_checks.sh` 是 shell 脚本，Windows 原生 pwsh 环境需经 git-bash/WSL 运行，技能未说明入口（低危）。
  - references/phase1-source-review.md 引用上游仓库路径 `skills/fluent2-design-system/references/tokens.md|components.md`——属历史来源记录而非本技能运行路径，不构成失效引用，但易被误读（低危/info）。
- **评价**：**可用**——结构最完整的一个技能，正文、参考文档、资源数据、模板代码、测试五层互相印证；仅余卫生类小问题。

## 3. ui-ux-pro-max

**文件**：SKILL.md（214 行）、references/ 2 个 md、scripts/ 4 个 py + tests/、data/ 17 个数据文件 + stacks/ 22 个 csv。无 README。

- **frontmatter**：`name: ui-ux-pro-max` 与目录名一致；description 除触发场景外还声明了数据规模（79 searchable styles (50 active)、192 palettes、74 font pairings、119 UX guidelines、105 icons、17 GSAP presets、25 chart types、22 stacks）✓。
- **数据规模逐项核实（重点项，全部吻合）**：
  - styles.csv：88 数据行，Status 分布 = active 50 / supplemental 29 / deprecated 9 → searchable 79（= 50+29）✓，与 data/catalog-summary.json（total 88 / searchable 79 / active 50）一致；
  - colors.csv 192 行、products.csv 192 行、ui-reasoning.csv 192 行 ✓；typography.csv 74 行 ✓；ux-guidelines.csv 119 行 ✓；icons.csv 105 行 ✓；motion.csv 17 行 ✓；charts.csv 25 行 ✓；stacks/ 恰好 22 个 csv，与 SKILL.md 列出的 22 个 stack 名称一一对应 ✓。
- **正文完整性**：214 行完整——when to apply、10 级优先规则表、Query Contract、4 步工作流（含 --design-system / --persist / dials / --domain / --stack）、0 结果兜底规则、示例、输出格式、Tips 表。无 TODO/占位符/截断。
- **支撑文件逐项核对**：
  - references/quick-reference.md 存在，且含 §1–§10 全部编号章节，SKILL.md Tips 表引用的 §3/§5/§6/§7/§8/§9 均能对应 ✓；
  - references/pro-rules.md 存在，含 SKILL.md 所指的 "Pre-Delivery Checklist (canonical)" 章节 ✓；
  - scripts/search.py、core.py、design_system.py、reasoning_contract.py 存在 ✓；ui-reasoning.csv 等数据文件均在 ✓。
- **问题**：
  - SKILL.md 第 45 行写 "see README for install instructions if Python is missing"，但技能目录内**不存在 README.md**（中危——空引用，Python 缺失时用户无指引可看）。
  - 全部调用命令写死 `${CLAUDE_PLUGIN_ROOT}/.claude/skills/ui-ux-pro-max/scripts/search.py`，按 Claude 插件布局书写；在本工作区 `skills/ui-ux-pro-max/` 布局下该路径不成立，agent 需自行改写路径（低-中危，可移植性）。
  - scripts/ 及 scripts/tests/ 下亦残留 `__pycache__/*.pyc`（低危卫生问题）。
- **评价**：**可用**——本地数据集真实齐全且与自述规模完全一致，是三处技能中数据治理最好的一个；仅需修掉 README 空引用并补充路径说明。

## 4. document-helper

**文件**：仅 SKILL.md（18 行）。

- **frontmatter**：`name: document-helper` 与目录名一致；description 存在但过于笼统（"Company document drafting and formatting helpers"），触发场景说得简略。
- **正文完整性**：正文自我定位为 "Example skill for the `company` environment"，仅两句用途说明 + 两条 notes。**没有任何可执行指令、模板、格式规范或脚本**——作为"起草/格式化助手"是空壳。
- **支撑文件**：引用 `configs/company.yaml`，已在仓库根目录验证存在 ✓。
- **过时/失效内容**：无失效引用；问题是内容缺失而非引用失效。
- **评价**：**不可用**（作为实际助手）——空壳示例：正文无可执行内容；若仓库有意将其作为环境示例保留，应在该定位下继续存在，但不应被当作可交付的文档起草能力。

## 5. internal-doc-search

**文件**：仅 SKILL.md（19 行）。

- **frontmatter**：`name: internal-doc-search` 与目录名一致；description 简略但范围明确（"Intranet-only internal documentation search helper"）。
- **正文完整性**：同样是 "Example skill for the `intranet` environment" 空壳——无检索指令、无工具名、无查询模式。
- **支撑文件核对（引用全部真实）**：`configs/intranet.yaml` 存在 ✓；`INTERNAL_DOC_URL` 在仓库根 `.env.example` 第 22 行确有声明 ✓；`agentctl update`、`agentctl import` 两个子命令在 agentctl/cli.py 中实际注册（第 68、113 行）✓——正文对"本机不跑 update、用离线包 import"的描述与 CLI 实现一致。
- **过时/失效内容**：无。
- **评价**：**不可用**（作为实际助手）——空壳示例，但其引用的配置与命令全部真实存在，骨架正确，只缺实质指令。

## 6. jira-helper

**文件**：仅 SKILL.md（18 行）。

- **frontmatter**：`name: jira-helper` 与目录名一致；description 点出范围（tickets、sprints、queries）。
- **正文完整性**："Example skill for the `company` environment" 空壳——无 JQL 示例、无 API/CLI 命令、无工单流转说明。
- **支撑文件核对（引用全部真实）**：`configs/company.yaml` 存在 ✓；`COMPANY_TOKEN` 在 `.env.example` 第 19 行确有声明 ✓。
- **过时/失效内容**：无。
- **评价**：**不可用**（作为实际助手）——空壳示例，引用的配置与密钥声明真实存在，缺实质工作流内容。

## 7. onenote

**文件**：SKILL.md（116 行）、agents/openai.yaml。

- **frontmatter**：`name: onenote` 与目录名一致；description 详尽列出全部触发场景（搜索、列出/读取/创建 notebook/section/page、追加/替换内容、附件、删除）✓。
- **正文完整性**：116 行完整——Tool Map（12 个 `mcp__onenote.*` 工具）、4 步工作流、创建/更新页面的 JSON 示例（含 attachments）、安全规则（删除前确认、避免全量曝光隐私）、故障排查（登录指引、找不到页面、编辑目标歧义、Markdown 丢排版）。无 TODO/占位符/截断。
- **支撑文件**：agents/openai.yaml 存在且与正文一致（声明依赖 `onenote` MCP 服务器）✓。正文不引用本地脚本/数据。
- **运行依赖核验（环境观察）**：本机 PATH 上**未检出 `onenote-mcp`** CLI；当前会话工具集中亦无 `mcp__onenote.*`。技能正文已内置优雅降级（"If the OneNote MCP tools are unavailable, say the OneNote channel is not connected"），故缺失不会导致错误行为，只会无法工作。故障排查给出的 client ID `14d82eec-204b-4c2f-b7e8-296a70dab67e` 为微软知名的 Microsoft Graph PowerShell 第一方 client ID，拼写合理。
- **过时/失效内容**：正文本身无过时内容。
- **评价**：**基本可用**——正文完整且自洽，但运行完全依赖外部 OneNote MCP 集成，本机/本会话均未检出该依赖；未配置时按文中规则安全降级。

## 8. research

**文件**：SKILL.md（12 行）、agents/openai.yaml。

- **frontmatter**：`name: research` 与目录名一致；description 清楚（对一手权威来源做调研并把结论落成仓库内 Markdown 文件）✓。
- **正文完整性**：12 行但**完整可执行**：启动后台 agent → 只追一手来源（官方文档、源码、规范、第一方 API）→ 每条结论引用出处 → 写成单个 Markdown 文件 → 按仓库既有惯例存放。三步闭环，无占位符。
- **支撑文件**：正文不引用本地文件；agents/openai.yaml 与之匹配 ✓。
- **过时/失效内容**：无。
- **评价**：**可用**——极简但自洽，无任何外部依赖。

## 9. domain-modeling

**文件**：SKILL.md（74 行）、ADR-FORMAT.md（47 行）、CONTEXT-FORMAT.md（60 行）、agents/openai.yaml。

- **frontmatter**：`name: domain-modeling` 与目录名一致；description 明确触发场景（统一语言/术语、记录架构决策、供其他技能维护领域模型）✓。
- **正文完整性**：74 行完整——单/多上下文文件结构、会话中的 5 项行为（对照词汇表挑战、磨尖模糊术语、具体场景压测、与代码交叉验证、就地更新 CONTEXT.md）、ADR 三条件门槛。无 TODO/占位符/截断。
- **支撑文件逐项核对**：正文引用的 `./CONTEXT-FORMAT.md`、`./ADR-FORMAT.md` 均存在 ✓，且两个格式文档本身完整（CONTEXT-FORMAT 含单/多仓判定规则，ADR-FORMAT 含模板、编号、qualify 清单），交叉引用（SKILL.md ↔ 两个 FORMAT）互指一致。
- **过时/失效内容**：无。
- **评价**：**可用**。

## 10. codebase-design

**文件**：SKILL.md（114 行）、DEEPENING.md（37 行）、DESIGN-IT-TWICE.md（44 行）、agents/openai.yaml。

- **frontmatter**：`name: codebase-design` 与目录名一致；description 明确触发场景（设计/改进模块接口、寻找深化机会、决定 seam 位置、可测性，及供其他技能使用深模块词汇）✓。
- **正文完整性**：114 行完整——词汇表（Module/Interface/Implementation/Depth/Seam/Adapter/Leverage/Locality，含 each 的 Avoid 词）、深/浅模块图示、4 条原则、可测性设计 3 例（含 TypeScript 代码）、关系定义、rejected framings、进阶指引。无 TODO/占位符/截断。
- **支撑文件逐项核对**：正文引用的 `DEEPENING.md`、`DESIGN-IT-TWICE.md` 均存在 ✓；两个支撑文档反向引用 SKILL.md 一致，DEEPENING 与 DESIGN-IT-TWICE 之间也互相引用，闭环成立；DESIGN-IT-TWICE 的并行 sub-agent 流程具体可执行。
- **过时/失效内容**：无。
- **评价**：**可用**。

---

## 问题清单

| 技能 | 问题 | 严重程度 | 建议 |
|---|---|---|---|
| ui-ux-pro-max | SKILL.md 写 "see README for install instructions if Python is missing"，但目录内不存在 README.md（空引用） | 中 | 补一个含安装说明的 README.md，或删改该句改为内联说明 |
| ui-ux-pro-max | 调用命令写死 `${CLAUDE_PLUGIN_ROOT}/.claude/skills/ui-ux-pro-max/scripts/search.py`，在本工作区 `skills/` 布局下路径不成立，需 agent 改写才能运行 | 中 | 在 SKILL.md 注明按实际技能根目录解析（如 `skills/ui-ux-pro-max/scripts/search.py`），或同时给出插件布局与仓库布局两种写法 |
| onenote | 运行依赖 `mcp__onenote` MCP 服务器与 `onenote-mcp` CLI，本机 PATH 与当前会话均未检出；依赖缺失时技能只能降级提示 | 中（环境依赖，正文无缺陷） | 使用前先完成 OneNote MCP 配置与 `onenote-mcp login`；正文已内置降级与排查指引，无需改动 |
| document-helper | 空壳示例：正文 18 行，无任何可执行指令/模板/脚本，description 也偏笼统 | 低（自我声明为示例；若按实际能力要求则为高） | 若需真实能力：补具体模板、格式规范与检查清单；否则保持示例定位并在汇总报告中标注"非交付能力" |
| jira-helper | 空壳示例：无 JQL 示例、无工作流说明（引用的 configs/company.yaml 与 COMPANY_TOKEN 均真实存在） | 低（同上） | 同上：补真实工作流或维持示例定位 |
| internal-doc-search | 空壳示例：无检索指令（引用的 configs/intranet.yaml、INTERNAL_DOC_URL、agentctl update/import 均真实存在且与 CLI 实现一致） | 低（同上） | 同上：补实际检索流程或维持示例定位 |
| pyside6-fluent-ui | tests/、scripts/ 残留 `__pycache__/*.pyc`（共 8+ 个）；scripts/run_checks.sh 为 shell 脚本，Windows 原生环境需 bash 且无说明 | 低 | 清理 `__pycache__`；为 run_checks 提供等价 .ps1 入口或在 README 说明运行方式 |
| pyside6-fluent-ui | references/phase1-source-review.md 引用上游仓库路径 `skills/fluent2-design-system/...`（历史来源记录，非本技能运行路径，易被误读为缺失文件） | 低 | 无需修改文件内容；可在该文档头部注明"上游来源记录，路径属上游仓库" |
| qt-ui-design | README.md 的 Files 表仅列 SKILL.md，未列 LICENSE.txt | 低 | 顺手补全（不阻塞使用） |
| ui-ux-pro-max | scripts/ 与 scripts/tests/ 残留 `__pycache__/*.pyc` | 低 | 清理缓存目录 |

## 审计方法备注

- 数据规模比对命令：pwsh `Import-Csv` 统计 styles.csv 的 Status 分布；逐文件 `Measure-Object -Line` 核对各 CSV 行数（结果与 catalog-summary.json 交叉验证）。
- JSON 有效性：pwsh `ConvertFrom-Json` 逐个解析 pyside6-fluent-ui/resources/ 下 5 个 JSON。
- 命令存在性：`agentctl/cli.py` 中 grep `add_parser(` 确认 update/import 子命令；`.env.example` 中 grep 确认 COMPANY_TOKEN / INTERNAL_DOC_URL；`Get-Command onenote-mcp` 确认 CLI 未检出。
- 类名/路径存在性：对 pyside6-fluent-ui 全目录 grep 正文点名的 5 个标识符；对 references/*.md 中所有 `references|resources|scripts|templates|examples/...` 路径逐个与目录清单比对。
