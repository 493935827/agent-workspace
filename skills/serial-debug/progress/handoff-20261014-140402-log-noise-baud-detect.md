# Handoff：GUI 日志降噪 + Windows 串口工具修复 + 主动波特率检测

- 对话标识：DSH Web GUI 本地会话（对话 ID/链接在本环境不可用；以本文件时间与内容标识本对话）。
- 归档时间：2026-10-14 14:04（Asia/Shanghai）。
- 项目根：`D:\App\agent-workspace\skills\serial-debug`（Git 仓库根为其上级 `agent-workspace` 单仓，remote `origin` = `github.com/493935827/agent-workspace`）。

## 目标与范围

用户在 Qt 串口工作台 + Windows 共享串口工具链上的三项连续请求：

1. GUI 直发模式下，提示符之间的 `按键字节 0d '\r'` TX 行与空 RX 行不要打印。
2. `按键字节 08 '\x08'` 这类信息**默认**也不要打印（引出"默认关闭 + 开关"设计）。
3. 修复 Windows 菜单「自动检测串口并连接」（用不了），并新增自动检测波特率功能。

## 本次完成（均已验证）

### 1. GUI 日志降噪（commit `2ed0ad6`、`cb4af8d`，已推送）

- 直发模式所有按键的「按键字节」TX 记录默认静默（回车、退格、方向键、普通字符）；字节计数照常累计。
- 新增会话选项 `show_keybytes`（默认 False）+ 设置页「显示按键字节」复选框（`显示 TX` 下方），按会话持久化，打开后逐键打印。
- 空提交（裸回车、空命令、空宏行）不生成 TX 记录（`poll()` 的 `sent` 分支 `if shown:`）。
- 空行修复在 `render_record` 片级：行首无可见内容的片段（`\r\n` 回显、peer 写入的裸 CR）跳过渲染；行中空片仍负责收尾当前行；records 与落盘日志不受影响。
- 演示入口 `serial_gui_qt_prototype.py` 的 `direct_send` 同步为开关控制。
- 测试：`tests/test_ui_log_noise.py` 8 项。

### 2. Windows「自动检测串口并连接」修复（commit `e6989e5`，已推送）

根因是三层叠加，全部修掉：

- **配置编码损坏**：`serial_config.local.psd1` 被 PS 5.1 无显式编码的 GBK 读写（`Set-LocalSerialPort`/`Set-LocalBaud` 里 `Get-Content -Raw`）损坏，中文注释乱码并吞掉 `Port` 行 → Port 键丢失。修复：两处 `Set-Local*` 读写统一 `-Encoding UTF8` + `UTF8Encoding($true)` 写回；本地配置已重建为干净 UTF-8 BOM（Port=COM6、Baud=115200，gitignored 本地文件）。
- **报错难懂**：Port 缺失 → `--port ""` 空元素 → PS 5.1 `Start-Process -ArgumentList` 拒绝，报 "Cannot validate argument on parameter 'ArgumentList'"。修复：`Start-SerialBridge`/`Find-SerialBaud` 开头对缺失 Port 快速报「本地配置缺少 Port…请选菜单 5 或 8」。
- **设计缺陷**：菜单 5 只认"新插入"的口（板子已插着时等 120 秒超时）；桥运行时直接 throw 拒绝。重做 `Detect-AndConnectNextSerialPort`：优先 `detect_serial_port.py --pick-now` 选择已接入 USB 串口（VID/PID 齐全、排除蓝牙），无 USB 口才回退 `Find-NextSerialPort` 等待；桥运行中同口直接开终端、换口征询确认（`-Action DetectConnect` 传 `-NonInteractive` 不询问）。

### 3. 主动波特率检测（commit `e6989e5`，已推送）

- `windows/detect_serial_baud.py` 新增 `--active`：每个候选波特率发送回车探测（`probe_baud`，探测次数 `--attempts` 默认 2），应答沿用原被动评分与拒绝猜测规则（`rank_samples` 公共化）；主动模式默认 `--seconds 0.5`、`--min-bytes 4`；`--probe` 支持转义（默认 `\r`，可 `help\r`）。
- 菜单 10 二选一（1 主动默认 / 2 被动），检测成功后可按提示立即启动桥并开终端；`-Action AutoBaud` 默认主动、只存配置不启动。
- `windows/detect_serial_port.py` 新增 `--pick-now`（无 USB 候选 exit 5），`port_map`/`detect_next_port` 支持注入枚举器以便测试。

### 4. GUI「自动检测串口」按钮修复（随本 handoff 一并提交）

用户复测后确认此前"自动检测 COM 口不行"指的是 **Qt 工作台左侧「自动检测串口」按钮**（现象：板子已插着时没反应/一直等待）——与控制台菜单 5 同源的设计缺陷：旧逻辑只认"新插入"的口，弹窗还默认停在「等待新设备插入」。修复（`scripts/serial_gui_qt.py`）：

- 新增 `is_usb_serial`/`usb_serial_rank`（与 `windows/detect_serial_port.py` 同规则：VID/PID 齐全、排除蓝牙、自然序）。
- `detect()` 重做：唯一已接入 USB 串口**直接连接不弹窗**；多个 USB 候选弹列表（USB 在前、最优预选、含描述，其余端口排在后面）；无 USB 串口才进入等待模式（快照来自已取的端口列表）。安装目录 `C:\Users\E0465\.agents\skills\serial-debug` 是指向本仓库的 junction，用户运行的就是仓库内代码（已核实）。
- 测试：`tests/test_ui_detect.py` 4 项（唯一 USB 直连、多 USB 预选排序、无 USB 回退等待+插入触发、排序纯函数）；全套 51 项通过（offscreen 约 62 秒）。



- 全套 51 项测试通过（PySide6 offscreen，约 62 秒）；新增 `test_detect_serial_baud.py` 5 项主动用例 + `tests/test_detect_serial_port.py` 5 项 + `tests/test_ui_detect.py` 4 项。
- COM6（FTDI，atom>> shell）实机：`--pick-now` 选中 COM6（跳过两个蓝牙口）；`--active` 8 候选×3 轮检出 115200（exit 0）；`-Action Start` 桥启动成功（修复前报 ArgumentList 错）；`-Action DetectConnect` 走「已接入 USB → 桥同口 → 直接开终端」全链路，miniterm 中看到板子持续输出 `I/RRAM_TEST ... cimsub0 test_line: NNN` 日志；`-Action Stop` 正常释放。
- 检测期间向设备发送了少量回车探测字节（与空闲提示符按回车等价，已向用户说明）。

## 关键决策与被否决做法（避免重复）

- **按键字节静默选"发送时读开关"**（`direct_send` 传 `shown=None`，`sent` 事件跳过建记录），而非"记录打标记 + 渲染过滤"：更简单，且空提交静默语义统一；代价是开关不回溯显示历史按键（接受）。
- **空行修复必须在片级而非记录级**：设备回显 `\r\natom>>` 常为单批记录，记录级过滤无法消除行首空片产生的空行；行中空片绝不能跳过（负责收尾当前提示符行，且退格擦除的 view/record 尾部同步依赖它）。
- **`AnsiLogParser.feed` 会把 `\r` 归一成 `\n` 并吞 CRLF 的 LF**——真实 RX 路径的空行是空字符串片段；`peer_tx` 等直灌记录才带裸 `\r`。两种都按 `not part.strip()` 判空白。
- **`serial_console.ps1` 是 CRLF + UTF-8 BOM**：edit 工具多行匹配会失败（LF 不匹配）且重写文件会剥 BOM（PowerShell 5.1 随即按 ANSI 误读中文）。做法：多行替换用"临时文件（write 工具）→ pwsh `.Replace`（归一化 CRLF）→ `[IO.File]::WriteAllText` + `UTF8Encoding($true)` 写回"，单行编辑可用 edit 工具但事后必须补 BOM；改完用 `Parser::ParseFile` 语法检查 + 控制器 `-Action Status` 冒烟。
- **Start-Process 空元素报错是表象**，真根因在配置编码；不要只对 `$Arguments` 做空值过滤了事。
- **推送环境**：本机直连 GitHub 被 RST，需一次性 env 走本地代理 `127.0.0.1:7897`（`HTTPS_PROXY`/`HTTP_PROXY` 且清 `NO_PROXY=*`）；裸 `git push` 命令会被某层拦截器损坏 argv（git 收到自身路径为子命令），用 `git -C . push origin master` 形态绕过。

## 剩余工作 / 下一步

1. **设备级 RX 往返人工验收**（历史遗留项）：现有 COM6 板持续输出 RRAM_TEST 日志，正好可补被动波特率检测实测 + `send` 后 RX 应答验收；注意板子在跑测试，验收前先与用户确认是否要停。
2. **style token 改动同步上游 serial-gui 仓库**（github.com/493935827/serial-gui，2026-10-13 遗留，本次未做）。
3. **GUI 侧「自动检测波特率」按钮**（用户未要求，仅备忘）：可复用 `windows/detect_serial_baud.py` 的 `detect_baud_active`/`score_sample`，线程模式仿 `SerialWorker`。
4. 仓库根上级出现 `../serial-debug.7z`（未跟踪），非本对话产物，未处理、未提交。

## 运行状态 / 临时产物

- 无遗留后台任务：miniterm 验证任务已杀、串口桥已停止、COM6 已释放；`tests/` 下临时诊断脚本（diag_detect、verify_enter_silent、_diag_start*、_guard_*、_ps1_*）均已删除。
- 工作树干净，`master` 与 `origin/master` 同步（本对话提交 `2ed0ad6`、`cb4af8d`、`e6989e5` 均已推送；其间有一次非本对话的提交 `4fec1d1 fix(bundle)`，已随分支推送，未改动）。
- 本地配置 `windows/serial_config.local.psd1` 已重建（UTF-8 BOM；Port=COM6、Baud=115200）。

## 建议技能

- `serial-debug`（串口工作流与发送前宣告约定）、`git-delivery`（收尾提交推送约定）。建议不构成调用授权。
