# 交接记录：serial-gui Qt 主分支切换与 serial-debug skill 工具同步

记录时间：2026-10-13 16:32（Asia/Shanghai）
对话：本次对话未取得可核实的会话 ID 或链接；以本归档文件与 `progress/progress.md` 中 2026-10-13 的行识别本次交接。

## 当前目标与范围

用户要求：serial-gui 先提交推送 → 检查 Tk/Qt 两版差异 → 若 Qt 版落后则更新 → 将 Qt 版设为主分支并把本地切到 Qt → 更新 serial-debug skill 里的工具。中途用户澄清：希望 agent 接管功能做进 Qt 工作台之后再替换 skill 里的薄客户端（而非简单并存或只改文档）。

涉及三个 Git 仓库：

| 仓库 | 路径 | 远程 |
| --- | --- | --- |
| serial-gui | `D:\App\serial_tool\serial-gui` | github.com/493935827/serial-gui |
| agent-workspace（本项目根） | `D:\App\agent-workspace` | github.com/493935827/agent-workspace |
| serial-debug（skill 规范仓库） | 无本地常驻克隆（本次用临时克隆同步后已删除） | github.com/493935827/serial-debug |

## 本次完成

1. **serial-gui 提交推送**：工作区本就干净，将本地领先的 `6da8cea`（2026-10-10 backspace 回显修复）推送到 origin/main。
2. **Tk/Qt 差异检查**：Qt 分支 `codex/serial-qt-preview`（fork 自 `2b01f45`，2026-09-11）落后 main 两块——`6da8cea` backspace 修复和 9-11 之后的 6 份交接文档。
3. **Backspace 修复移植到 Qt 树**（`e6973f1`）：`serial_common.py` 解析器保留 `\x08`/`\x7f` 标记；Tk 会话照 main 原实现移植（新增 `append_records(records, history=)` 入口）；Qt 接收路径原地改写记录并裁剪视图。Tk 带 main 的 6 项测试，Qt 新增 7 项镜像测试。
4. **Qt 设为主分支**（`54829dc`）：main 文档合入 Qt 分支（`serial_gui.py` 冲突取 Qt 侧），main fast-forward 到 Qt tip；本地已切到 main；`codex/serial-qt-preview` 已并入、远程保留，可择机删除。
5. **服务会话与 agent 接管做进 Qt 工作台**（`50fe938`）：
   - 新增 `serial_service_client.py`：协议 v1 客户端（与 skill 的 `serial_client.py` 协议兼容）。
   - 新增 `ServiceWorker` 线程：与 `SerialWorker` 相同事件契约（opened/rx/sent/error/closed），另有 `service_state`（服务状态）、`peer_tx`（他人/Agent 写入）、`send_failed`（发送被拒或结果未知）。
   - 工作台 UI：菜单「更多 → 连接共享服务…」；状态栏显示 服务/设备/控制权；设置页「终止 Agent 并接管」按钮（owner=agent 时可用）；会话配置随设置持久化（`service` 字段，保存/恢复均校验）。
6. **skill 工具替换**（agent-workspace `6cb72ab`，规范仓库 `c3dc773`）：
   - 删除 `skills/serial-debug/scripts/serial_gui.py`（50 行服务薄客户端）；内置 Qt 工作台 5 文件：`serial_gui_qt.py`、`serial_gui_qt_prototype.py`、`serial_common.py`、`serial_service_client.py`、`qt-preview-tokens.json`（prototype 在 import 时读取该数据文件，缺它工作台起不来）。
   - `windows/serial_gui.cmd` 指向 `serial_gui_qt.py`；README 中英文 GUI 章节改写（直连 vs 共享服务两种用法、互斥规则、接管流程）。
   - `tests/test_serial_gui.py` 重写为「工作台 ↔ 真实 SerialService」契约测试；无 PySide6 环境自动跳过。
7. **进度记录**：serial-gui `progress/progress.md`（`878fe8f`）、agent-workspace 根 `progress/progress.md`（`22b2890`）均已更新。

全部推送成功：serial-gui main → `878fe8f`；agent-workspace master → `22b2890`；serial-debug main → `c3dc773`（https://github.com/493935827/serial-debug/commit/c3dc773）。

## 验证证据

- serial-gui：offscreen 全套 88 项 + 9 子测试通过（pytest，`.venv`），含 7 项新服务会话测试（连接/RX、发送回环、接管、对端 TX、服务不可达、断开语义、配置持久化）。
- skill：全套 18 项通过（用 serial-gui 的 `.venv` 跑，含工作台对真实 SerialService 的连接/发送/接管/断开链路）；无 PySide6 的 workspace `.venv` 中 GUI 测试按设计跳过。
- `git diff --check` 通过；规范仓库同步时 `serial_common.py:238` 有既有的 EOF 空行提示（源自 serial-gui 上游、progress 已记录的已知项，非本次引入）。

## 已实现未验证 / 遗留

- **真实硬件验收**：无板卡；真实 COM 口上直连、共享服务、拔插、DTR/RTS、长期流均未实测。
- **真实共享服务端到端**：工作台对真实服务的联调仅在测试内（FakeSerial 设备）验证；`serial_service_cli.py` + 工作台 + Agent 三方实际联机未做。
- **Tk 初始化环境抖动**：`test_serial_alerts` 在本机 uv 版 Python 3.12 下间歇性 Tcl init 失败（干净树三轮复现，每轮用例不同），与代码无关；换官方 CPython 或修复 Tcl 安装可消除。
- `dist\agent-workspace-v0.1.0-offline\workspace\skills\serial-debug` 离线快照已过期（仍是薄客户端版），下次打包需重新生成。

## 剩余工作与下一步

1. 真实板卡验收 Qt 工作台（直连 + 共享服务两种模式），对照旧版差异清单走查。
2. 可选清理：删除 serial-gui 远程 `codex/serial-qt-preview` 分支（已并入 main）。
3. 可选清理：`.venv` 的 Tk 抖动如需根治，改用官方 CPython 建 venv。
4. 下次打包 agent-workspace 离线包时重新生成 dist 快照。
5. workspace `.venv` 如需跑 skill GUI 测试，需补装 PySide6（当前无）。

## 阻塞

无。三仓库均已提交并推送成功。

## 关键决策与拒绝过的方案

1. **skill 更新方式**：用户在「并存 / 替换 / 只改文档」三选项外加提问「Qt 工作台能否加入 agent 接管」，最终选择「先做接管再入库」——即先把服务会话做进 Qt 工作台，再以它替换薄客户端。未采纳简单并存（双 GUI 分工）与只改引用。
2. **ServiceWorker 事件契约**：复用 `SerialWorker` 的 opened/rx/sent/error/closed 事件种类，让 records/宏/提醒/视图管线零改动；新增 `service_state`/`peer_tx`/`send_failed` 三类。曾考虑在 GUI 线程直接调 `agent.takeover`，改为 worker 线程 `takeover` Event 转发，避免阻塞 GUI。
3. **对端 TX 显示**：用 job 事件（终态 `written` 且 job_id 不在本方 pending）配对 tx 字节缓冲，消除「tx 先于 send 调用返回到达」的竞态；本方发送只经 `sent` 事件记录一次，不重复显示。
4. **Qt erase 语义**（backspace 移植）：只回删 RX 记录尾部字符，不越换行、不吃 TX/本地通知（比 Tk 版更保守）；HEX 显示继续展示 raw 真相（含 `08` 标记）。
5. **规范仓库同步边界**：工作区 `AGENTS.md` 的 progress 约定（引用 `progress/progress.md`）刻意不同步到 serial-debug 规范仓库（该仓库无 progress/）；`windows/requirements.txt` 仅尾部空行差异，不动。
6. **测试工厂**：skill 集成测试的 `serial_factory` 每次返回新 `FakeSerial`（`serial.open` 会关闭再重开设备，复用同一实例会拿到已关闭对象导致 'unknown' 发送结果）。

## 相关入口

- serial-gui：`serial_gui_qt.py`（Workbench/ServiceWorker）、`serial_service_client.py`、`tests/test_qt_runtime.py`（FakeService + ServiceSessionTests）
- skill：`skills/serial-debug/scripts/serial_gui_qt.py` 等 5 文件、`skills/serial-debug/tests/test_serial_gui.py`、`skills/serial-debug/README.md`
- 测试环境：serial-gui 仓库内 `.venv`（pyserial + PySide6 + pytest；Tk 抖动见上）
- 本仓库相关提交：`6cb72ab`（skill 替换）、`22b2890`（根进度）；serial-gui：`e6973f1`/`54829dc`/`50fe938`/`878fe8f`；规范仓库：`c3dc773`

## 建议技能

- 真实硬件验收前：`serial-debug`（连接共享串口前必读硬件安全说明）。
- 发现缺陷时：`diagnosing-bugs`；修复后收尾：`git-delivery`。
