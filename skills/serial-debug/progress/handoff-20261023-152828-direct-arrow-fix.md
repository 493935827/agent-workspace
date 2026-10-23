# Handoff：直发模式 ←/→ 导致预输入回显消失修复

- 日期：2026-10-23 15:28（Asia/Shanghai）
- 对话 ID/链接：本环境不可见（未记录，见「未知项」）
- 仓库：`agent-workspace`（monorepo，本 skill 位于 `skills/serial-debug/`），分支 `master` → `origin/master`

## 目标与范围

修复用户报告：当前 GUI 直发模式下按 ←/→ 方向键导致「预输入显示」（设备回显出的已输入命令行）消失。范围仅限 Qt 工作台（`serial_gui_qt.py` + 共享 `serial_gui_qt_prototype.py`），不含固件侧。

## 根因（已证实）

- 直发模式按键映射（`serial_gui_qt.py` `eventFilter` 视图分支、`serial_gui_qt_prototype.py` `LogView.keyPressEvent`）把 ←/→ 转成 `ESC[D`/`ESC[C` 发给设备。
- 日志是追加式显示（`serial_common.py` `AnsiLogParser` 注释明确"not a cursor terminal"），无法呈现行内光标移动；预输入行只能靠设备回显呈现。
- 仅回显/仅历史型 shell（如 COM6 `atom>>`）对光标左移以退格类字节应答；GUI 的退格擦除逻辑（`ERASE_CHARS = '\x08\x7f'` → `erase_received`/`erase_view`）随即把已渲染的回显输入行逐字符抹掉 → "预输入显示消失"。
- 排除项：命令模式输入框 ←/→ 正常（QLineEdit 标准行为，无过滤器拦截，有测试锁定）；GUI 无名为"预输入"的功能（全量 UI 字符串扫描确认）；GUI 侧唯一能抹除显示的机制就是退格字节。

## 本次完成

1. 修复：直发模式 ←/→ 不再发送，落到本地只读光标移动；↑/↓ 历史、Enter/退格/Tab/Esc 等按键逐字节保留。
   - `scripts/serial_gui_qt.py` `eventFilter` keys 表移除 `Key_Right`/`Key_Left`（含原因注释）
   - `scripts/serial_gui_qt_prototype.py` `LogView.keyPressEvent` keys 表同步移除（真实 GUI 事件先经 app 级 filter 落到 view，两处必须一致）
2. 新增回归 `tests/test_ui_direct_arrows.py` 4 项（先红后绿）：方向键不出设备、回显输入行在按键后存活、历史/编辑键字节不变、命令框光标编辑照常。
3. 全量测试 127 项绿（原 123 + 新增 4，offscreen ~11 分钟）；唯一 warning 为既有 GBK 子进程解码噪声，与本改动无关。
4. 提交并推送：`476f765` fix(serial-debug) + `941cd34` docs(progress) → `origin/master`（推送通道照旧：`git -c alias.push= -c credential.helper= -c credential.helper=manager push origin master` + `NO_PROXY=""`/`HTTPS_PROXY=http://127.0.0.1:7897`/`GCM_INTERACTIVE=never`）。
5. `progress/progress.md` 概况已加一行（直发模式 ←/→ 修复，`941cd34`）。

## 已实现未验证 / 下一步

- **实机验收待板子**（COM6，atom>> shell）：连接 → 直发模式点日志区打字（如 `version`）→ 按 ←/→ 数次 → 回显输入行应保持不动；↑/↓ 历史召回、退格、Enter 照常。
- 若用户实际想要"←/→ 在 shell 内真正移动光标编辑"（终端级行编辑），需 GUI 实现本地行缓冲+光标渲染，是新功能，不在本次范围；已向用户说明。

## 决策与拒绝方案

- 选择"不发送 ←/→"而非"修改退格擦除逻辑"：擦除逻辑本身正确（设备真退格必须擦，有既有测试），问题在发送了显示无法呈现的光标移动字节；追加式日志下发送 ←/→ 对任何设备行为都不可能得到正确渲染（退格应答→抹行；重绘应答→重复行）。
- Home/End/Delete/Insert/PgUp/PgDn 映射**保持原样**（最小修复，仅动被报告的 ←/→）；同类风险存在但设备语义因 shell 而异，未扩大改动面。
- 复用既有约定：验证走先红后绿；测试基建用 `FakeWorker` + `dispose_window` 模式（见 `test_ui_log_noise.py`）。

## 文件与证据

- 修复：`scripts/serial_gui_qt.py:1295-1305`（eventFilter keys 表）、`scripts/serial_gui_qt_prototype.py:672-679`（LogView keys 表）
- 测试：`tests/test_ui_direct_arrows.py`（新增 140 行，4 用例）
- 概况：`progress/progress.md`（新增修复行 + 归档行）
- 排障脚本（临时，`%TEMP%\serial_repro\`）：`arrow_probe.py`（EchoShell 三模式 offscreen 探针）、`cmdbox_probe.py`、`trace_probe.py`、`strings.py`；它们驱动了定位（FakeSerial 缺 `in_waiting` 属性、offscreen 下 fresh 会话默认 mode=1/命令框禁用等事实）

## 未知项

- 本对话 ID/链接本环境不可见；续接对话如需引用请以本归档路径为准。
- 用户板子 shell 对 ←/→ 的确切应答字节未抓取（无硬件）；根因按"GUI 侧唯一擦除机制=退格字节"反推，修复对该机理的所有变体（退格应答/无应答/重绘应答）均有效。

## 建议 skills（不构成调用授权）

- `git-delivery`：修复收尾已按其流程提交推送；后续任务改动同。
- `diagnosing-bugs`：如实机验收发现新症状再排障时使用。
