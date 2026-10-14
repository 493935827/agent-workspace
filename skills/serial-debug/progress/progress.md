# 项目进度

最后更新：2026-10-14 11:30（Asia/Shanghai）

## 当前概况

- 日志降噪（2026-10-14）：直发模式「按键字节」TX 记录改为默认全静默（含回车、退格等控制键），新增「显示按键字节」开关（日志显示设置页，默认关闭）供调试不回显设备时打开；空提交（裸回车、空命令、空宏行）不生成 TX 记录但字节数照常累计；行首无可见内容的 RX 片段（回车回显 CRLF、peer 写入的裸 CR）不再渲染成纯时间戳空行，行中空片仍正常收尾当前行。显示过滤不影响 records 与落盘日志。新增 `tests/test_ui_log_noise.py`（8 项），全套 36 项通过（offscreen 约 41 秒）。
- 目标 / 当前阶段：Issue #1 共享串口工具已完成 Phase 1 服务端；2026-10-13 人工 GUI 升级为 Qt 工作台；同日完成统一风格改造（详见 docs/design-system.md）；2026-10-14 完成 skill 完整工作流实测与工作流级 bug 修复。
- 工作流全链路验证（2026-10-14）：Windows 控制器（Status/Start/Send/Ports/Stop，PID 跟踪与进程清理含 uv shim 场景）、bridge/connect/send 三客户端、managed service 生命周期（released 启动、serial.open、send、send.hex、serial.close、断连保护、service.stop --expect-pid）、agent 租约（acquire、占用拒绝、带凭证发送、release）全部实测通过；Conserver 未安装（按规则跳过）。
- 真实硬件验收（COM6，FTDI USB 串口）：被动波特率检测跑完 8 候选×3 轮全程无输出（正确拒绝猜测）；115200 打开成功，`help` TX 已写入（exit=0），终端与日志无 RX——对端设备不发送数据，设备级应答往返仍需有输出的目标板配合（人工验收项保留）。
- 工作流 bug 修复（2026-10-14）：README/windows README 增补 uv/PEP 668 的 `.venv` 安装路径（原 `pip install` 文档在 uv 管理 Python 上必失败）；`serial_gui.cmd` 优先使用仓库内 `.venv` 解释器（系统 Python 缺 PySide6 时双击不再失败，已冒烟验证）；文档化 PowerShell 5.1 给 `serial_control.py` 传 JSON 需用 `--%` 停止解析符；troubleshooting.md 修正 `--timeout-ms`/`--reset-dtr`/`serial_reconnected` 三个不存在的参数与事件引用。
- 测试环境注记：全量 28 项测试在 offscreen 平台约 27 秒（与 2026-10-13 记录一致）；真实显示器平台约 339 秒，差异为窗口管理开销，非回归。
- 统一风格（2026-10-13）：定为「Fluent 2 深色优先开发者终端」，规范文档在 `docs/design-system.md`，token 唯一事实源仍为 `scripts/qt-preview-tokens.json`。
- 风格改造内容：token 对比度修复（浅色 text_secondary/brand 系、深色 danger_foreground，全部达 WCAG AA 4.5:1，品牌色回归 Fluent 官方 #0f6cbd）；首次启动默认深色；Tab 键仅在命中宏时消费（否则正常焦点遍历）；搜索框加宽至 220px；状态栏错误以 danger 色保持 8 秒（修复 30ms 内被轮询覆盖的 bug）；四个对话框改为行内校验错误（不再弹模态警告框、失败不关窗）。
- 新增测试：`tests/test_ui_tokens.py`（token 对比度守卫，无需 Qt）、`tests/test_ui_style.py`（深色默认/持久化、Tab、状态栏错误、行内错误、搜索宽度，8 项）。
- 测试基建修复：`tests/test_shared_serial_bridge.py` 的 FakePort 增加 park()（bridge 守护线程泄漏的 service reader 热循环会饿死同进程后续测试，全量套件 287s→27s）；test_ui_style 的窗口清理用 deleteLater+冲刷 DeferredDelete（PySide6 信号连接滞留导致 setStyleSheet 二次方变慢）。
- 全套 28 项测试通过（PySide6 6.12 offscreen 环境，约 27 秒）；双主题截图像素采样验证（浅/深主题 chrome 与 canvas 颜色正确）。
- 跨仓库契约测试：`tests/test_serial_gui.py` 保持「Qt 工作台 ↔ 真实 SerialService」集成测试不变；服务端、协议、桥、`serial_control.py` 均未改动。
- Qt 工作台自身的完整测试（含 FakeService、backspace 回显、服务会话）在 serial-gui 仓库维护（github.com/493935827/serial-gui）。
- 下一步：设备级应答往返需有串口输出的目标板配合人工确认；style token 改动需同步上游 serial-gui 仓库（本次未同步）。

## 对话归档

| 日期 / 对话 | 完成内容 | 交接 |
| --- | --- | --- |
| 2026-10-14 / 日志降噪 | 按键字节记录默认全静默并新增「显示按键字节」开关；空提交静默；行首空白 RX 片段跳过渲染（记录与日志保留）；新增 8 项回归测试，全套 36 项通过 | （本次对话，未单独归档） |
| 2026-10-14 / 工作流全链路实测与修复 | loop:// 与 COM6 实测控制器/桥/客户端/服务生命周期/agent 租约；修复 uv venv 安装文档、serial_gui.cmd .venv 优先、PS 5.1 JSON 传参说明、troubleshooting 陈旧参数；28 项测试通过（offscreen 27s） | （本次对话，未单独归档） |
| 2026-10-13 / 统一风格与可访问性改造 | 定档 Fluent 2 深色优先；token AA 修复、深色默认、Tab/状态栏错误/对话框行内校验修复；新增对比度与风格回归测试；测试基建提速 287s→27s | [Fluent2 style pass](handoff-20261014-110900-fluent2-style-pass.md) |
| 2026-10-13 / Qt 工作台替换薄客户端 | Qt 工作台加入服务会话与 agent 接管；skill 内置并重写集成测试；18 项测试通过 | （本次对话，未单独归档） |
| 2026-09-09 / Serial Phase 1 implementation | 完成服务、CLI、GUI、中文说明并推送；GUI 接管冒烟仍未完全通过 | [Serial Phase 1](handoff-20260909-160606-serial-phase1.md) |
