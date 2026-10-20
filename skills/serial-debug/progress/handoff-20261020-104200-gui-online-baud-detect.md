# Handoff：GUI 在线波特率检测接入 + 服务端连接中检测 + 提交切分

- 对话标识：DSH Web GUI 本地会话（对话 ID/链接在本环境不可用；以本文件时间与内容标识本对话）。
- 归档时间：2026-10-20 10:42（Asia/Shanghai）。
- 项目根：`D:\App\agent-workspace`（Git 仓库根，remote `origin` = `github.com/493935827/agent-workspace`，分支 `master`）。

## 目标与范围

用户在 serial-debug 工具链上的三段连续请求：

1. 「当前的自动检测并连接功能用不了」——复诊；并讲解自动检测波特率用法。
2. 「自动检测波特率我想在串口连接后也能进行，如果波特率中途改变了，能感知到并打印正确字符」——服务端/桥在线检测能力。
3. 「serial_console.cmd 我要用 cli？我想直接在 gui 用」——把在线检测与自动感知接入 Qt 工作台。

## 本次完成（均已验证）

### 1. 复诊「自动检测并连接用不了」（结论：功能未坏）

- 当前机器只有 COM4/COM5 两个**蓝牙虚拟串口**（BTHENUM，无 USB VID/PID，按设计被排除）；上次验收用的 COM6（FTDI 板）不在系统。菜单 5 走到「没有已接入的 USB 串口，转为等待新插入」属预期行为。
- 验证：20 项检测相关单测 + loop:// 桥/send 冒烟通过；`5519739` 后代码未变。本地配置 `windows/serial_config.local.psd1` 完好（COM6/115200，UTF-8 BOM）。

### 2. 服务端「连接中波特率检测」（commit `af63f9c`，已推送）

- 新模块 `scripts/serial_baud_scan.py`：`readability`/`score_sample`/`rank_samples`（自 windows 检测脚本抽出的共享评分核心）+ `scan_open_device`（对已打开设备扫描候选，结束时总是恢复起始波特率，由调用方决定应用赢家）+ 监视常量（MONITOR_THRESHOLD=0.55 / WINDOW=3s / MIN_BYTES=48 / SCAN_SECONDS=0.5 / COOLDOWN 5/20s）。
- `scripts/serial_service.py`：RX 乱码监视（`_reader` 内 `_auto_baud_feed` 滑窗）→ `_auto_baud_loop` 线程扫描（`transition='baud_scan'` 暂停收发）→ 应用赢家 + `baud_changed`/`baud_scan` 事件 + raw 终端注入「[串口桥] 波特率已从 X 切换为 Y」提示；控制动作 `serial.autobaud`（异步触发）/`autobaud.status`/`serial.autobaud.configure`；**被动为默认，主动探测须显式开启（hardware-safety 约束）**；agent 租约期间自动扫描挂起，手动触发不受影响；手动 `serial.baud` 改波特率也发事件+提示。
- `scripts/shared_serial_bridge.py`：`--autobaud/--autobaud-probe/--autobaud-bauds/--autobaud-seconds/--autobaud-rounds` 启动参数；`autobaud` 在线检测子命令（exit 0/2/3/4/5/6，机器行 `autobaud_result:`）。
- Windows 控制器（`serial_console.ps1`，CRLF+UTF-8 BOM，改法见下）：`Start-SerialBridge` 透传 `--autobaud*`（配置 `AutoBaudMonitor` 默认开 / `AutoBaudProbe` 默认关 / `AutoBaudSeconds=0.5` / `AutoBaudRounds=1`）；菜单 10 新增方式 3「在线检测（保持串口桥运行）」，成功后可把新波特率写回本地配置；`serial_config.psd1` + local 增加新键。
- 修过的真 bug：空样本 `score=-inf` 进入事件 → `json.dumps(allow_nan=False)` 抛错 → **订阅流整体断掉**（GUI/客户端收不到后续事件）；`readability` 需把 U+FFFD（decode 替换符，`isprintable()` 为 True）再扣掉。

### 3. GUI 接入（commit `67255ca`，已推送）

- 直连会话（SerialWorker）：工作线程内乱码监视 + `_run_scan`（扫描期间 RX/TX 自然暂停——扫描在同一线程独占串口）；会话级开关 `autobaud_monitor`（默认开）/`autobaud_probe`（默认关）随会话持久化。**注意：`SerialWorker(options=整个会话字典)`，会话级开关在 `options['options']`，不是顶层。**
- 服务会话（ServiceWorker）：`controls` 队列 → `serial.autobaud`；pump `baud_scan`/`baud_changed` → `baud_notice`/`baud_changed` 事件。
- Workbench：「日志设置」页两个复选框 + 「在线检测波特率」按钮；「更多」菜单同名入口（QInputDialog 选被动/主动）；poll() 渲染 `baud_notice`（SYS 行）与 `baud_changed`（更新 `s['baud']`/`s['service']['baud']` + SYS 行）。测试用 `mock.patch('serial_gui_qt.SCAN_SECONDS', 0.02)` 缩短扫描。
- 测试 `tests/test_ui_autobaud.py` 4 项；测试设备 `DriftSerial`（test_serial_service.py）补了 `in_waiting` 属性。
- windows/README.md 增加工作台段落；references/shared-bridge.md 增加在线检测/子命令/exit codes。

### 4. 提交切分（用户选择「分两个提交都推送」）

工作树曾同时含本对话改动与并行会话的连接修复（对方 progress 记录注明「待用户决定提交切分」）。做法：对两个混合文件（`serial_service.py`、`test_serial_service.py`）构造「HEAD+仅对方改动」的中间版本（临时脚本 `_split_commit1.ps1`，用后已删），先提交对方修复 `c6c3afa`，再恢复完整副本提交本对话 `67255ca`。**注意**：`67255ca` 的 `serial_gui_qt.py` 顺带带入了并行会话当时在工作树里的「共享串口桥分组/一键停止」代码（提交信息未覆盖该功能），对方已在 `4695a90` 用补提交（仅测试+文档）处理并记录——历史不再改写。

## 已实现未验证（实机验收，板子未接）

- **真实 UART 上的中途换波特率漂移**：插回板子后，把固件切到另一波特率，确认终端先出扫描提示、再出切换提示、之后字符恢复可读（GUI 直连会话 + miniterm 各验一次）。
- 被动波特率检测（菜单 10 方式 2 / `-Action AutoBaud -Passive`）与 GUI 在线检测的实机过一遍。
- 历史遗留：设备级 RX 应答往返（send 后确认设备回包）——RRAM_TEST 输出板具备条件，验收前先确认是否停板上的测试。

## 剩余工作 / 下一步

1. 实机验收（见上）；板子接回后菜单 5 会自动选中并写回配置。
2. style token 改动同步上游 serial-gui 仓库（github.com/493935827/serial-gui，2026-10-13 遗留）。
3. 未跟踪文件 `skills/serial-debug.7z`（多日前出现，非本对话产物）一直未处理，待用户定夺。

## 关键决策与被否决做法（避免重复）

- **自动检测被动为默认**（hardware-safety.md 硬约束）：主动探测（发回车）必须显式开启；GUI/控制器/服务三层默认一致。
- **扫描在 SerialWorker 读循环线程内串行执行**（而非独立线程）：天然独占串口、无需暂停原语；服务端则用 `transition='baud_scan'` + `scan_active` 让既有 _writer/_reader 暂停。
- **扫描器结束总是恢复起始波特率**，赢家由服务/worker 经统一路径应用——避免半应用状态。
- **事件载荷不得含 `-inf`/`NaN`**（协议 `allow_nan=False`），空样本分数置 `None`。
- **`windows/serial_console.ps1` 是 CRLF+UTF-8 BOM**：多行修改用「行级补丁脚本（UTF-8 BOM）+ `WriteAllLines`」或临时文件+`.Replace`；无 BOM 的补丁脚本会被按 GBK 解码导致中文损坏（本对话踩过并已恢复）。执行环境疑似按 GBK 读无 BOM 脚本——**补丁脚本务必转 UTF-8 BOM 再跑，且脚本内避免中文字符串**。
- **测试设备建模**：假设备 read 需有 ~1ms 字节节奏（否则错误波特率窗口把队列吸干、正确候选饿死）；扰动用按位取反（乘加扰动可能产生高可读率假乱码）；测试结束要 `disconnect_session` + `until(no worker)` 再关窗，否则残留 worker 向已关窗口灌事件拖慢后续用例（15.6s→6.7s）。
- **推送环境**：需一次性 env 走本地代理 `127.0.0.1:7897`（`HTTPS_PROXY`/`HTTP_PROXY`，清 `NO_PROXY`）；裸 `git push` 会被拦截器损坏 argv，用 `git -C <repo> push origin master` 或 `cmd /c` 形态。
- 客户端 `next_event(timeout)` 超时抛 `queue.Empty`，等待辅助必须捕获。

## 文件与状态

- 已推送：`af63f9c`（服务端在线检测）、`c6c3afa`（并行会话连接修复，按用户切分决定代为提交）、`67255ca`（GUI 接入）均在 origin/master。
- 本对话收尾时本地还有并行会话的 `4695a90`（共享桥分组/一键停止补提交，仅测试+文档；其代码已随 67255ca 推送）未推送——本 handoff 回合将其随交接提交一并推送。
- 工作树唯一遗留：未跟踪 `skills/serial-debug.7z`（非本对话产物，未提交未删除）。
- 验证证据：全套 77 项测试通过（offscreen，含本对话 +15 服务端/桥 +4 GUI + 并行会话 2+5 回归）；loop:// 端到端冒烟（在线检测子命令、`autobaud=on` 启动参数、send 往返）；ps1 `Parser::ParseFile` 语法检查 + Status/Start/Stop 冒烟。

## 运行状态 / 临时产物

- 无遗留后台任务；临时诊断/补丁脚本（`_patch_console.ps1`、`_split_commit1.ps1`、`diag_*`、`serial_loop__*.log`）均已删除。
- 会话期间串口无硬件接入；桥已停止（COM6 不存在，冒烟用 loop:// 已释放）。

## 建议技能

- `serial-debug`（串口工作流与发送前宣告约定）、`git-delivery`（收尾提交推送约定）。建议不构成调用授权。
