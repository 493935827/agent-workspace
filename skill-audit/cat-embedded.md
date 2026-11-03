# 分类深读审计：嵌入式 / 硬件 / 逆向 / 通信类技能（6 个）

> 审计范围：工作区 `D:\App\agent-workspace\skills` 下 6 个技能，逐个完整读取 SKILL.md 正文（非仅 frontmatter），并逐一核对引用的支撑文件与脚本参数。
> 审计方式：只读。未修改任何技能内容，未触碰 `dist\` 目录。
> 审计人：content-emb（任务 t5）。日期：本轮会话。

---

## 1. andes-aice-bringup

**frontmatter**：`name: andes-aice-bringup` 与目录名一致；description 详尽，明确列出触发症状（USB 无法打开、FTDI/libusbK 通道错绑、需先经 SPI 释放 CPU、寄存器读到 0xFFFFFFFF、JTAG scan all ones、ADX 下载 SRAM）并显式排除通用 OpenOCD 场景。✓

**正文**：63 行，完整无截断，无 TODO/占位符。bring-up 顺序（清理 USB → 释放 CPU → 再启动 ICEman）、失败信号、完成判据、UAC 提示均成体系。交叉引用 `serial-debug` 技能存在。✓

**引用支撑文件核对（逐个存在）**：

| 引用 | 状态 |
| --- | --- |
| `scripts/diagnose_aice.ps1`（70 行） | 存在，完整；枚举 FT2232 设备/驱动服务/ICEman 进程/监听端口（2354/4444/6666/9901），与文档一致 |
| `scripts/start_aice.ps1`（118 行） | 存在，完整；参数 `-ReleaseScript/-PythonExe/-IceRoot/-CygwinBash/-GdbPort 9901/-Config 14` 与文档示例一致；MI_00=libusbK / MI_01=FTDIBUS 校验、0xFFFFFFFF 失败判定均按文档实现 |
| `references/troubleshooting.md`（50 行） | 存在，按症状分支，与正文端口/驱动约定一致 |
| `references/sram-adx-debug.md`（125 行） | 存在，LMA/VMA 处理、GDB 验证、串口边界说明完整 |
| `agents/openai.yaml` | 存在，与技能定位一致 |

**过时/失效内容**：未发现失效命令或路径。所有 PowerShell cmdlet（Get-PnpDevice、Get-NetTCPConnection、pnputil /restart-device 等）均为 Windows 标准工具。

**问题**：
- 文档第 1 步要求"verify ports 2354, 4444, 6666, and 9901 are free"，但 `start_aice.ps1` 只停止 ICEman/openocd 进程，并不校验端口占用；端口检查只出现在 `diagnose_aice.ps1`（只读列出）。约定与脚本行为有轻微出入。（低）

**一句话评价**：**可用**——正文、脚本、参考文档三者参数与端口约定完全对齐，仅"端口空闲校验"一条文档要求未在启动脚本中强制。

---

## 2. firmware-mentor

**frontmatter**：`name: firmware-mentor` 与目录名一致；`disable-model-invocation: true` 与 `agents/openai.yaml` 的 `allow_implicit_invocation: false` 一致，也与工作区 AGENTS.md"仅用户显式 `$firmware-mentor` 时加载"的规则一致。description 为人物定位式（"面向初级固件与嵌入式工程师的中文技术导师"），未写触发场景语句——但该技能设计上只允许显式调用，故影响有限。✓

**正文**：82 行，完整；核心准则、按请求类型路由参考文件、通用工作流、输出质量检查齐全。✓

**引用支撑文件核对（7 个全部存在，且全部通读）**：

| 引用 | 状态 |
| --- | --- |
| `references/firmware-knowledge-map.md`（130 行） | 存在，完整 |
| `references/debugging-workflow.md`（124 行） | 存在，完整；与正文的"事实/推测/待验证/缺失"四标签体系一致 |
| `references/code-and-manual-review.md`（102 行） | 存在，完整 |
| `references/learning-roadmap.md`（109 行） | 存在，完整 |
| `references/career-paths.md`（80 行） | 存在，完整 |
| `references/project-interview-guide.md`（80 行） | 存在，完整 |
| `references/answer-templates-and-examples.md`（118 行） | 存在，完整；6 个示例与路由表呼应 |

**过时/失效内容**：无。全文未引用具体版本号、路径或外部工具名，通用性强。

**一句话评价**：**可用**——正文与 7 份参考文件全部完整且互相一致；唯一可挑之处是 description 没有触发场景描述（受"仅手动调用"设计约束，属可接受）。

---

## 3. reg-to-ll（含嵌套 workflow-run-skill）

**外层 frontmatter**：`name: reg-to-ll` 与目录名一致；description 交代了输入（本地 Excel / 离线飞书快照）与产物（SVD、CMSIS 头文件、LL Driver）。✓

**外层正文**：仅 10 行，是刻意的"薄入口"——命令、阶段名、结果字段全部下放给 [workflow-run-skill/SKILL.md](../skills/reg-to-ll/workflow-run-skill/SKILL.md)（"唯一事实源"），并给出机器可读的完成判据（退出码 0 + `valid=true` + `can_continue=true`）。设计如此，不算缺陷。✓

**嵌套技能 workflow-run-skill**：

- **frontmatter**：`name: workflow-run`，**与目录名 `workflow-run-skill` 不一致**。（低）
- 正文 63 行完整：唯一执行边界、local/feishu 两条命令模板、稳定结果契约（stages 排序、generated_this_run/available/validated/cache_hit 四事实不可互替、not-run 规则）。
- `reference.md`（72 行）存在且完整，命令接口与阶段顺序与 SKILL.md、实现三方一致。
- `run_workflow.py`（15 行）为薄适配器 → `workflow_runner.py`（814 行），六阶段（input-convergence → svd-generation → svd-parity → svd-validation → header-generation → ll-generation）全部有真实实现，非桩代码。

**引用/依赖核对（逐个存在）**：

| 引用 | 状态 |
| --- | --- |
| `workflow-run-skill/run_workflow.py` | 存在 |
| `workflow-run-skill/SKILL.md`、`reference.md` | 存在 |
| `workflow_runner.py`（814 行，完整实现） | 存在；`from compatibility.* import` 的 `SvdConvConfig/generate_header/generate_ll/OracleStatus/run_oracle/compare_svd_outputs/serialize_legacy_svd/validate_svd` 及 `input_convergence` 的两个加载函数均已确认定义 |
| `compatibility/{__init__,header,ll,oracle,oracle_runner,svd,svd_validation}.py` | 全部存在；`oracle.py` 内部引用同目录 `oracle_runner.py`（第 245 行）✓ |
| `input_convergence.py`、`workbook_model.py` | 存在 |
| `.reg-to-ll-install.json` | 存在；清单文件列表与实际目录一一对应，含各文件 SHA-256，安装于 2026-08-27，source_commit 固定为 `9579b71` |

**过时/失效内容**：

- **`feishu-fetch` 技能缺失（中）**：workflow-run-skill 明确要求"飞书输入：先由 `feishu-fetch` 获得重建 Excel 和原始 JSON 快照"。已在三处技能目录（工作区 `skills/`、`~\.agents\skills`、`~\.codex\skills`）用 `**/*feishu*` 全量检索，均不存在该技能。飞书输入链路在本地不可用；本地 Excel 链路（`--source local`）不受影响。
- **"对应的 check Skill" 悬空（低）**：嵌套 SKILL.md 写"若用户只想检查已有文件，请使用对应的 check Skill"，三处技能目录均无对应 check 技能。
- **嵌套 frontmatter name 与目录名不一致（低）**：`workflow-run` vs `workflow-run-skill`。
- 嵌套 SKILL.md 命令示例 `python workflow-run-skill/run_workflow.py ...` 以 reg-to-ll 根目录为工作目录，与外层 SKILL.md 的入口说明一致，可执行。

**一句话评价**：**基本可用有小问题**——本地 Excel → SVD → 头文件 → LL 驱动链路完整且带自校验清单；但飞书输入依赖的 `feishu-fetch` 技能本地缺失，且嵌套技能 name 与目录名不一致、"check Skill"引用悬空。

---

## 4. serial-debug

**frontmatter**：`name: serial-debug` 与目录名一致；description 极详尽（共享 UART/RS-232/USB-serial/COM、人工与 agent 并发、TCP bridge 优先、Conserver 备选）。✓

**正文**：131 行，完整无截断，无 TODO。工作流（菜单 / 直启桥 / 人工终端 / proc:// 进程终端 / agent 连接 / Conserver / 重同步）闭环。

**引用支撑文件核对（逐个存在；先前 glob 结果被截断，故全部按精确文件名二次核实）**：

| 引用 | 状态 |
| --- | --- |
| `scripts/shared_serial_bridge.py`（450 行） | 存在；argparse 实测含文档所列全部子命令与参数：`bridge`（`--port/--baud/--host/--tcp/--chardelay/--log/--control/--proc-args/--proc-cwd/--autobaud*`）、`connect`（`--host/--tcp/--encoding/--line-ending/--backspace-mode`）、`send`（`--newline/--line-ending/--idle/--max-wait/--expect/--expect-timeout`）、`autobaud`。退出码 0/2/3/4 语义与 SKILL.md、windows/README.md 三处一致 |
| `scripts/serial_control.py`（71 行） | 存在；action 参数透传 `agent.acquire/heartbeat/release/takeover`（动作实现位于 `serial_service.py`/`serial_commands.py`，已确认） |
| `scripts/serial_commands.py`、`serial_protocol.py`、`serial_service.py`、`serial_service_cli.py`、`serial_gui_qt.py`、`serial_common.py` | 全部存在 |
| `references/shared-bridge.md` | 存在；SKILL.md 指向的「Process Terminal Bridges (proc://)」小节（第 29 行）存在 |
| `references/conserver.md`、`console-client.md`、`hardware-safety.md`、`troubleshooting.md` | 全部存在 |
| `windows/serial_console.cmd`、`serial_console.ps1`、`serial_config.psd1`、`serial_gui.cmd`、`README.md`、`requirements.txt` | 全部存在；README 中 `-Action` 清单、租约流程（`agent.acquire` → 带token发送 → `agent.release`）与 SKILL.md 一致 |
| `tests/test_serial_commands.py` | 存在（SKILL.md 未引用，属附加资产） |

**过时/失效内容**：脚本参数、退出码、租约语义在文档与实现三处互相印证，未发现失效命令。

**问题**：
- `references/mcp.md`（12 行）未被 SKILL.md 的 References 列表或任何其他文件引用，属孤立文档（内容本身自洽、短小）。（低）
- 技能目录内置完整 `.venv`（6700+ 文件，含 PySide6/Qt6 全套 DLL）及 `scripts/__pycache__`、`tests/__pycache__` 的 `.pyc`。`windows/README.md` 确实把 `.venv` 作为推荐运行环境引用（指向 `.venv\Scripts\python.exe`），属有意为之，但使 skill 目录体积与整洁度明显劣化。（低）
- SKILL.md「Source Maintenance」指向 `github.com/493935827/serial-debug`，离线无法验证仓库可达性（信息项）。

**一句话评价**：**可用**——功能链路（桥/终端/控制/租约/参考文档）完整且文档-脚本参数逐项吻合；仅存在孤立文档与内置 .venv 的仓库卫生类小问题。

---

## 5. reverse-engineer-anything

**frontmatter**：`name: reverse-engineer-anything` 与目录名一致；description 明确适用与排除条件（跳过普通源码仓库分析）；`metadata.version: "42"`。✓

**正文**：355 行，完整。连接策略（能连则直连、缺工具再走恢复流程）、按目标类型路由（ASAR/归档/APK/托管 PE/固件/浏览器/Electron/抓包/信号/WASM/EVM/Go/Rust/SQLite/PE 资源/ELF/core/IDA/Kuna）、summary-first、分阶段调查法、完成规范，结构清晰。✓

**来源与许可**：`UPSTREAM.md` 记录上游 morluto/rea、标签 `rea-agents-6.7.0`、对应提交 `27dc42d`；根目录 `LICENSE`（MIT）存在。UPSTREAM 声称"SKILL.md 和六份 references/ 按上游原样收录"——实际 references 恰为 6 个，吻合。✓

**引用支撑文件核对（逐个存在）**：

| 引用 | 状态 |
| --- | --- |
| `references/connection-and-recovery.md`（127 行） | 存在，含故障→处置对照表与 setup/dry-run 流程 |
| `references/native-and-artifacts.md`（297 行） | 存在 |
| `references/javascript-applications.md`（218 行） | 存在 |
| `references/android-applications.md`（36 行） | 存在 |
| `references/evidence-workflows.md`（71 行） | 存在 |
| `references/runtime-observation.md`（78 行） | 存在；SKILL.md 锚点 `#fiddler-everywhere-traffic-debugging` 对应标题「Fiddler Everywhere traffic debugging」（第 65 行）存在 |

**过时/失效内容**：

- **支持客户端列表两处不一致（低）**：SKILL.md 列 15 个客户端（…commandcode, vscode, grok_build, omp, grok_bot），而 `connection-and-recovery.md` 列 23 个（多出 qwen_code、trae、pi、hermes、qoder、droid、zcode、dsh）。SKILL.md 的列表相对自身参考文档偏旧；两处均建议未知客户端用 `doctor --json` 探测，功能影响小。
- 多处外部 GitHub 文档链接（`github.com/morluto/rea/blob/main/docs/*`）：外部资源，离线无法验证可达性（信息项）。

**一句话评价**：**可用**——正文与 6 份参考全部完整、锚点有效、上游版本有据可查；仅 SKILL.md 与参考文档的客户端清单有一处版本漂移。

---

## 6. pack-to-dts

**frontmatter**：`name: pack-to-dts` 与目录名一致；description 直接列出触发短语（"打包到DTS/下到DTS/离线包/离线安装"）与覆盖场景（pip/npm/URL/GitHub Release/本地目录/VSIX）。✓

**正文**：126 行，完整：意图判断树、触发短语表、统一参数、5 条脚本工作流、输出格式、注意事项。无 TODO/截断。✓

**引用支撑文件核对（逐个存在）**：

| 引用 | 状态 |
| --- | --- |
| `scripts/pack-pip.py` | 存在；`--packages/--python-version 3.10/--platform win_amd64/--output-dir/--output-name/--index-url/--extra-index-url` 与文档一致（文档第 5 条"默认 3.10 + win_amd64"与脚本默认值吻合） |
| `scripts/pack-npm.py` | 存在；`--packages/--registry/--output-dir/--output-name` |
| `scripts/pack-url.py` | 存在；`--urls/--rename/--output-dir/--output-name` |
| `scripts/pack-local.py` | 存在；`--paths（\|分隔）/–flatten/--output-dir/--output-name` |
| `scripts/pack-vsix.py` | 存在；`--extensions（\|分隔）/–version latest` |
| `scripts/common.py`（71 行） | 存在；7z 定位/打包/使用说明生成/摘要完整 |

**过时/失效内容**：

- **--output-dir 默认值文档与实现不符（低-中）**：SKILL.md「统一参数」表称 `output-dir` "默认 `D:\trash\Work\Innostar-ic\DTS` 或用户指定"，但 5 个脚本全部把 `--output-dir` 声明为 `required=True`，没有任何默认值。正文示例命令均显式传参，实际使用影响小，但按文档"省略参数"会直接报错。
- **触发意图与调用策略相悖（低）**：description 写"只要涉及…就使用本 skill"（面向自动触发），而 `agents/openai.yaml` 设 `allow_implicit_invocation: false`——Codex 侧不会隐式调用。可能是有意限制，但与 description 的强触发语气不一致。
- `scripts/__pycache__/common.cpython-312.pyc` 残留在技能目录（低）。
- `common.py` 在本机未装 7-Zip 时自动从 `https://www.7-zip.org/a/7zr.exe` 下载 7zr.exe——外部网络依赖，内网环境会失败（信息项，README 亦提示需离线部署场景）。

**一句话评价**：**可用**——五条打包脚本链路完整、参数与文档基本吻合；仅"output-dir 默认值"文档失实与隐式调用策略两处小问题。

---

## 问题清单总表

| 技能 | 问题 | 严重程度 | 建议 |
| --- | --- | --- | --- |
| reg-to-ll | 飞书输入链路依赖的 `feishu-fetch` 技能在三处技能目录（workspace skills/、~\.agents\skills、~\.codex\skills）均不存在 | 中 | 安装 feishu-fetch，或在 workflow-run-skill/SKILL.md 注明飞书链路需先具备该技能/给出替代获取方式 |
| reg-to-ll（workflow-run-skill） | frontmatter `name: workflow-run` 与目录名 `workflow-run-skill` 不一致 | 低 | 统一两者（改 name 或改目录名；注意同步 `.reg-to-ll-install.json` 清单） |
| reg-to-ll（workflow-run-skill） | "若用户只想检查已有文件，请使用对应的 check Skill"指向的 check 技能本地不存在 | 低 | 补充该 check 技能或删除该句引用 |
| pack-to-dts | 文档称 `--output-dir` 默认 `D:\trash\Work\Innostar-ic\DTS`，但 5 个脚本均 `required=True` 无默认值 | 低（中影响面） | 在脚本中补默认值，或修正 SKILL.md 参数表为"必填" |
| pack-to-dts | description 面向自动触发，`agents/openai.yaml` 却设 `allow_implicit_invocation: false` | 低 | 确认是否刻意；若希望短语自动触发则改策略，否则软化 description 语气 |
| serial-debug | `references/mcp.md` 未被任何文件引用（孤立文档） | 低 | 在 SKILL.md References 中列出，或删除该文件 |
| serial-debug | 技能目录内置完整 `.venv`（6700+ 文件）及 `__pycache__`/`.pyc` | 低 | 将 .venv 视为本地运行时而非技能内容，加入忽略清单；清理 __pycache__ |
| reverse-engineer-anything | SKILL.md 支持客户端列表（15 个）落后于 references/connection-and-recovery.md（23 个，含 qwen_code/trae/pi/hermes/qoder/droid/zcode/dsh） | 低 | 同步两处客户端清单（以较新为准） |
| andes-aice-bringup | 文档要求启动前"verify ports free"，`start_aice.ps1` 只停进程不校验端口占用 | 低 | 在脚本中加入端口占用检查，或将文档措辞改为"用 diagnose 脚本人工确认" |
| pack-to-dts | `scripts/__pycache__/common.cpython-312.pyc` 残留 | 低 | 清理 __pycache__ |

**信息项（不计入问题）**：serial-debug 与 pack-to-dts 存在外部网络依赖（GitHub 仓库同步、7-zip.org 下载 7zr.exe）；reverse-engineer-anything 的 morluto/rea 文档链接为外部资源；以上在离线/内网环境需留意，但不是技能结构缺陷。

## 可用状态汇总

| 技能 | 状态 | 一句话结论 |
| --- | --- | --- |
| andes-aice-bringup | 可用 | 文档-脚本-参考三者完全对齐，仅端口校验约定未在启动脚本强制 |
| firmware-mentor | 可用 | 正文与 7 份参考完整一致，description 无触发语句但受"仅手动调用"设计约束 |
| reg-to-ll（含 workflow-run-skill） | 基本可用有小问题 | 本地 Excel 链路完整且带安装清单自校验；飞书链路缺 feishu-fetch，name/目录名不一致 |
| serial-debug | 可用 | 功能链路完整、参数逐项吻合；存在孤立文档与内置 .venv 的卫生问题 |
| reverse-engineer-anything | 可用 | 355 行正文 + 6 份参考完整、锚点有效、上游 v42 有据可查；仅客户端清单漂移 |
| pack-to-dts | 可用 | 五条脚本链路完整；output-dir 默认值文档失实、隐式调用策略与 description 相悖 |
