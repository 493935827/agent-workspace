# 工作区 skills/ 目录审计清单（ws-auditor / t1）

- 审计对象：`D:\App\agent-workspace\skills`（工作区相对路径 `skills/`）
- 审计方式：只读。遍历全部一级子目录；逐个读取 `SKILL.md` 开头的 `---` frontmatter 块，提取 `name`、`description`；递归登记目录构成与嵌套 `SKILL.md`。未修改任何技能文件。
- 时间：2026 审计任务 t1 执行时
- 约束遵守：唯一写入文件为本文件；`dist\` 未触碰（仅在存在性比对中记录其镜像位置，见下）。

## 总览

- 实际技能目录数：**48**（任务预估 ~49；若把 `reg-to-ll/workflow-run-skill/` 嵌套技能计入，则 `skills/` 下共有 **49 个 SKILL.md 文件**，与预估数吻合）。
- `skills/` 根目录下另有 1 个非技能文件：`serial-debug.7z`（约 166 MB 压缩包，非技能目录，未展开）。
- 逐项检查结果：
  - 缺失 `SKILL.md`：**0 / 48**
  - frontmatter 缺失或 `---` 未闭合：**0 / 48**（48/48 均有合法 frontmatter 块）
  - frontmatter `name` 与目录名不一致：**0 / 48**（48/48 严格一致，含大小写）
  - `description` 空缺/明显缺失：**0 / 48**（48/48 均有非空 description）
- 结构观察（非缺陷，登记备查）：
  - **嵌套技能 1 处**：`reg-to-ll/workflow-run-skill/SKILL.md`（已知项，确认存在）。
  - **仅含 SKILL.md、无任何支撑文件的技能 10 个**：code-review、document-helper、find-skills、game-dev、git-delivery、git-helper、image-tools、internal-doc-search、jira-helper、python-helper。
  - **体积异常大的技能目录**：`serial-debug` 递归 6,720 个文件（含 `.venv/`、`build/`、`dist/`、`progress/` 等虚拟环境与构建产物，另有 `AGENTS.md`、`README.md`、`SerialWorkbench.spec`）；`ui-ux-pro-max` 90 个文件（data/、references/、scripts/）；`pyside6-fluent-ui` 80 个文件（含 LICENSE、NOTICE.md、SHA256SUMS、VERSION）。
  - **超长 description（>400 字符）5 个**：agent-reach(890)、pyside6-fluent-ui(760)、ui-ux-pro-max(495)、serial-debug(423)、andes-aice-bringup(401)。
  - **多行块标量 description**：agent-reach（14 行）、pyside6-fluent-ui（9 行）；qt-ui-design 为单行块标量，其余 45 个为单行内联。
  - **中英文 description 混用**：中文为主的有 firmware-mentor、git-delivery、pack-to-dts、project-structure、reg-to-ll；agent-reach 中英混合；其余以英文为主。
  - 多数技能带 `agents/` 子目录（子代理指引）；`qt-ui-design` 无 `agents/` 但带 `README.md`、`LICENSE.txt`；`reverse-engineer-anything` 带 `references/`、`LICENSE`、`UPSTREAM.md`。
- 镜像登记（非本次审计范围）：`dist/agent-workspace-v0.1.0-offline/workspace/skills/` 存在完整镜像（48 个技能目录 + 嵌套 workflow-run-skill，共 48 个 SKILL.md），本次未读取其内容，留给三处比对任务参考。

## 逐技能清单

图例：✅ = 存在/一致。目录构成列：`目录名; 文件名; N 文件`（N 为递归文件数）。description 摘要为浓缩转写，全文长度见备注。

| 目录名 | SKILL.md | frontmatter name | 与目录名一致 | description 摘要 | 备注（构成 / 递归文件数） |
|---|---|---|---|---|---|
| agent-reach | ✅ | agent-reach | ✅ | 全网调研/平台内容获取路由：15 平台（小红书/X/B站/Reddit/LinkedIn/YouTube/GitHub/RSS 等），OpenCLI/各平台 CLI/API 多后端；不负责内容加工与发帖写操作；SKILL.md 含路由表，复杂场景读 references/*.md | agents/; references/; SKILL.md; 8 文件；desc 890 字符、块标量 14 行（最长） |
| andes-aice-bringup | ✅ | andes-aice-bringup | ✅ | Andes AICE/ICEman 在 Windows 下的启动与诊断：USB 打不开、FTDI/libusbK 通道错绑、SPI 先释放 CPU 再 JTAG、寄存器读 0xFFFFFFFF、ADX 下载 SRAM 校验等 | agents/; references/; scripts/; SKILL.md; 6 文件 |
| ask-matt | ✅ | ask-matt | ✅ | 询问哪个技能/流程适合当前情况；本仓库技能集的路由器 | agents/; PHASE-BOUNDARIES.md; SKILL.md; 3 文件 |
| codebase-design | ✅ | codebase-design | ✅ | 深模块设计共享词汇：模块接口设计、深化机会、接缝划分、可测性 | agents/; DEEPENING.md; DESIGN-IT-TWICE.md; SKILL.md; 4 文件 |
| code-review | ✅ | code-review | ✅ | 结构化代码评审：正确性、风格、测试 | 仅 SKILL.md; 1 文件 |
| define-bounded-goal | ✅ | define-bounded-goal | ✅ | 定义/细化可度量 Goal：明确时间盒、工作深度、验证上限、安全停止规则与结构化交接 | agents/; SKILL.md; 2 文件 |
| diagnosing-bugs | ✅ | diagnosing-bugs | ✅ | 疑难 bug 与性能回归的诊断循环；"diagnose/debug" 触发 | agents/; scripts/; SKILL.md; 3 文件 |
| document-helper | ✅ | document-helper | ✅ | 公司文档起草与格式化辅助 | 仅 SKILL.md; 1 文件 |
| domain-modeling | ✅ | domain-modeling | ✅ | 构建/打磨项目领域模型：统一语言、术语、ADR 记录 | agents/; ADR-FORMAT.md; CONTEXT-FORMAT.md; SKILL.md; 4 文件 |
| find-skills | ✅ | find-skills | ✅ | 帮助发现与安装 agent 技能（"怎么做 X / 有没有技能能…"） | 仅 SKILL.md; 1 文件 |
| firmware-mentor | ✅ | firmware-mentor | ✅ | 面向初级固件与嵌入式工程师的中文技术导师 | agents/; references/; SKILL.md; 9 文件；中文 desc |
| game-dev | ✅ | game-dev | ✅ | 个人专用游戏开发辅助（引擎、资产） | 仅 SKILL.md; 1 文件 |
| git-delivery | ✅ | git-delivery | ✅ | 修改任务收尾：按改动范围验证、以一次完整修复为单位自动 Git 提交并推送授权远程；不用于只读分析 | 仅 SKILL.md; 1 文件；中文 desc |
| git-helper | ✅ | git-helper | ✅ | 日常 git 辅助：分支卫生、提交信息、安全撤销 | 仅 SKILL.md; 1 文件 |
| grilling | ✅ | grilling | ✅ | 对用户的计划/决策/想法做高强度追问（"grill" 触发词） | agents/; SKILL.md; 2 文件 |
| grill-me | ✅ | grill-me | ✅ | 用高强度访谈打磨计划或设计 | agents/; SKILL.md; 2 文件 |
| grill-with-docs | ✅ | grill-with-docs | ✅ | 高强度访谈打磨设计，并同步产出 ADR 与术语表 | agents/; SKILL.md; 2 文件 |
| handoff | ✅ | handoff | ✅ | 归档当前对话、生成提前续接提示、维护项目进度索引；Git+远程配置好时提交推送；内网机器须用户要求才提交 | agents/; SKILL.md; 2 文件 |
| image-tools | ✅ | image-tools | ✅ | 个人专用图像处理与生成辅助 | 仅 SKILL.md; 1 文件 |
| implement | ✅ | implement | ✅ | 按 spec 或一组工单实现工作 | agents/; SKILL.md; 2 文件 |
| improve-codebase-architecture | ✅ | improve-codebase-architecture | ✅ | 扫描代码库深化机会 → 可视化 HTML 报告 → 对选中项 grill | agents/; HTML-REPORT.md; SKILL.md; 3 文件 |
| internal-doc-search | ✅ | internal-doc-search | ✅ | 仅内网可用的内部文档搜索辅助 | 仅 SKILL.md; 1 文件 |
| jira-helper | ✅ | jira-helper | ✅ | 公司 Jira 工作流辅助（工单、sprint、查询） | 仅 SKILL.md; 1 文件 |
| onenote | ✅ | onenote | ✅ | 通过 `mcp__onenote` MCP 工具操作 OneNote：搜索、列笔记本/分区、读/建/改/附加页面 | agents/; SKILL.md; 2 文件 |
| pack-to-dts | ✅ | pack-to-dts | ✅ | 下载任意文件/包并打包为 7z 离线压缩包（pip、npm、URL、GitHub Release、本地目录、固件/工具链等）；"打包到DTS/离线包/离线安装" 触发 | agents/; scripts/; .gitignore; SKILL.md; 10 文件；中文 desc |
| project-structure | ✅ | project-structure | ✅ | 初始化项目/规划目录与文档结构、决定文件归属时使用；普通内容修改、只读任务不触发 | agents/; references/; SKILL.md; 3 文件；中文 desc |
| prototype | ✅ | prototype | ✅ | 构建一次性原型回答设计问题：状态模型合理性、UI 感受 | agents/; LOGIC.md; UI.md; SKILL.md; 4 文件 |
| pyside6-fluent-ui | ✅ | pyside6-fluent-ui | ✅ | 按 Microsoft Fluent 2 原则构建/审计/重构 PySide6 Qt Widgets 界面：语义明暗 token、QPalette、QSS、可访问状态、可选 VS Code 风格工作台壳；不引入 React/WinUI/XAML/QML | agents/; examples/; references/; resources/; scripts/; templates/; tests/; LICENSE; NOTICE.md; SHA256SUMS; VERSION; SKILL.md; 80 文件；desc 760 字符、块标量 9 行 |
| python-helper | ✅ | python-helper | ✅ | Python 惯用法、打包与调试片段 | 仅 SKILL.md; 1 文件 |
| qt-ui-design | ✅ | qt-ui-design | ✅ | 为 Qt/QML、Qt 项目、web、嵌入式 MPU/MCU 目标设计或审计 UI/UX | LICENSE.txt; README.md; SKILL.md; 3 文件；无 agents/ 子目录 |
| reg-to-ll | ✅ | reg-to-ll | ✅ | 本地 Excel 或离线飞书快照经强制验证，生成可追溯的 SVD、CMSIS 头文件与 LL Driver | compatibility/; workflow-run-skill/（**嵌套技能** workflow-run-skill\SKILL.md）; .reg-to-ll-install.json; input_convergence.py; workbook_model.py; workflow_runner.py; SKILL.md; 15 文件；中文 desc |
| research | ✅ | research | ✅ | 对高信任一手来源调研并把结论写成仓库内 Markdown 文件 | agents/; SKILL.md; 2 文件 |
| resolving-merge-conflicts | ✅ | resolving-merge-conflicts | ✅ | 解决进行中的 git merge/rebase 冲突 | agents/; SKILL.md; 2 文件 |
| reverse-engineer-anything | ✅ | reverse-engineer-anything | ✅ | 用 REA 逆向 native/managed/Electron/打包/固件/浏览器目标：解释功能、比版本、反编译、指导重建；普通源码库架构分析不用 | references/; LICENSE; UPSTREAM.md; SKILL.md; 9 文件 |
| run-tickets | ✅ | run-tickets | ✅ | 以依赖感知的波次运行 /to-tickets 工单集（本地工单目录或 GitHub 父 issue）；仅用户显式调用并授权分支/worktree/提交/子代理时使用 | agents/; references/; scripts/; SKILL.md; 5 文件 |
| serial-debug | ✅ | serial-debug | ✅ | Codex 与 Claude Code 共享串口控制台调试：人机并发访问同一 UART/COM 口、命令注入、日志、防失步与超时恢复；Windows 优先内置 TCP bridge | .venv/; agents/; build/; dist/; docs/; progress/; references/; scripts/; tests/; windows/; .gitignore; AGENTS.md; README.md; SerialWorkbench.spec; SKILL.md; **6,720 文件**（含虚拟环境与构建产物，体积异常大） |
| setup-matt-pocock-skills | ✅ | setup-matt-pocock-skills | ✅ | 为本仓库配置工程技能：issue tracker、triage 标签词汇、领域文档布局；其他工程技能首次使用前运行一次 | agents/; domain.md; issue-tracker-github/gitlab/local.md; triage-labels.md; SKILL.md; 7 文件 |
| tdd | ✅ | tdd | ✅ | 测试驱动开发；"red-green-refactor" 或集成测试触发 | agents/; mocking.md; tests.md; SKILL.md; 4 文件 |
| teach | ✅ | teach | ✅ | 在本工作区内教用户新技能或概念 | agents/; GLOSSARY/LEARNING-RECORD/MISSION/RESOURCES-FORMAT.md; SKILL.md; 6 文件 |
| to-questionnaire | ✅ | to-questionnaire | ✅ | 把答不了的决定变成给他人填写的问卷 | agents/; SKILL.md; 2 文件 |
| to-spec | ✅ | to-spec | ✅ | 把当前对话综合成 spec 并发布到项目 issue tracker（不做访谈，只做综合） | agents/; SKILL.md; 2 文件 |
| to-tickets | ✅ | to-tickets | ✅ | 把计划/spec/对话拆成带阻塞边的 tracer-bullet 工单并发布到配置的 tracker（本地每票一文件或原生阻塞链接） | agents/; SKILL.md; 2 文件 |
| triage | ✅ | triage | ✅ | 按 triage 角色状态机处理 issue 与外部 PR：分类、验证、必要时 grill、写 agent-ready brief | agents/; AGENT-BRIEF.md; OUT-OF-SCOPE.md; SKILL.md; 4 文件 |
| ui-ux-pro-max | ✅ | ui-ux-pro-max | ✅ | Web/移动/桌面 UI/UX 设计智能；本地可检索数据：79 styles、192 palettes、74 字体配对、119 UX 指南、105 icons、17 GSAP presets、25 chart types、22 stacks | data/; references/; scripts/; SKILL.md; 90 文件；desc 495 字符 |
| wait-what | ✅ | wait-what | ✅ | 停下——上一条消息没传达成功，重新表述 | agents/; SKILL.md; 2 文件 |
| wayfinder | ✅ | wayfinder | ✅ | 把超出单会话容量的大块工作规划成 issue tracker 上的决策工单地图，逐个解决直到路径清晰 | agents/; SKILL.md; 2 文件 |
| wizard | ✅ | wizard | ✅ | 生成交互式 bash 向导，引导人完成只有人能做的步骤（基础设施、凭据、CI secrets、一次性迁移/cutover） | agents/; template.sh; SKILL.md; 3 文件 |
| writing-for-agents | ✅ | writing-for-agents | ✅ | 为 agent 写文档；创建/编辑技能或修改 AGENTS.md/CLAUDE.md 时使用 | agents/; SKILL-MECHANICS.md; SKILL.md; 3 文件 |

## skills/ 之外的散落 SKILL.md（只记位置与归属，未展开审查）

全工作区检索（排除 `skills/`、`dist/`、`node_modules/`、`.venv/`、`.git/`）共命中 **2 处**，均为已知项，均属工作区内 vendored 的 XERJ 仓库（`projects/xerj`），不是工作区技能库成员：

| 位置 | frontmatter name | 归属说明 | 体量 |
|---|---|---|---|
| `projects/xerj/docs/case-studies/wordpress-security-audit/skill/SKILL.md` | `xerj-security-audit` | XERJ 仓库自带的白盒安全审计技能文档（WordPress 案例研究配套），跟随 vendored 仓库进入工作区 | 128 行 / 7,637 字节 |
| `projects/xerj/tools/xerj-code/SKILL.md` | `xerj-code` | XERJ 仓库 reference-coding 工具（`tools/xerj-code/`）自带的技能文档 | 587 行 / 38,473 字节 |

补充：除以上 2 处与 `skills/`、`dist/` 镜像外，工作区内无其他 SKILL.md；`skills/` 下亦未发现小写变体（Windows 大小写不敏感过滤已覆盖）。

## 问题汇总

按任务要求的三类缺陷口径：

1. **缺失 SKILL.md**：无（48/48 目录均有）。
2. **frontmatter name 与目录名不一致**：无（48/48 严格一致，含大小写）。
3. **description 空缺或明显缺失**：无（48/48 均为非空；其中 2 个为多行块标量、其余为单行）。

供汇总报告参考的登记性发现（非缺陷）：

- 任务预估 49 个技能目录，实际一级目录 48 个；把 `reg-to-ll/workflow-run-skill/` 嵌套技能计入后，`skills/` 下 SKILL.md 恰为 49 个。
- `skills/` 根下有非技能文件 `serial-debug.7z`（约 166 MB），建议在报告中提示是否移出技能根目录。
- `serial-debug/` 内含 `.venv/`、`build/`、`dist/`、`progress/` 等运行产物（合计 6,720 个文件），是全部技能中体积/文件数异常项；本次按约束未读取其内容，仅登记构成。
- 10 个技能为"裸 SKILL.md"（无 agents/、references/ 等任何支撑文件）：code-review、document-helper、find-skills、game-dev、git-delivery、git-helper、image-tools、internal-doc-search、jira-helper、python-helper。
- 超长 description（>400 字符）5 个：agent-reach(890)、pyside6-fluent-ui(760)、ui-ux-pro-max(495)、serial-debug(423)、andes-aice-bringup(401)——若后续做规范化可关注触发词密度与长度上限。
- `dist/agent-workspace-v0.1.0-offline/workspace/skills/` 为工作区 skills/ 的完整镜像（48 个 SKILL.md，含嵌套），三处比对任务可将其作为第四处参考位置。
