# 项目进度

最后更新：2026-10-20 10:46（Asia/Shanghai）

## 当前概况

- 目标 / 当前阶段：serial-debug skill 全链路（服务端 + Qt 工作台 + Windows 控制器 + bridge/客户端）持续迭代；Issue #1 Phase 1 已完成，进入实机验收与打磨期。
- 已完成并验证：Windows 控制器全工作流（含 uv shim 场景）；Qt 工作台 Fluent 2 深色风格与可访问性改造；GUI 日志降噪（按键字节默认静默 + 「显示按键字节」开关，`2ed0ad6`/`cb4af8d`）；菜单 5「自动检测串口并连接」重做并修复配置编码损坏根因、主动波特率检测（`e6989e5`）；GUI「自动检测串口」按钮重做（唯一已接入 USB 口直连、多候选预选列表、无 USB 才等待）；COM6 实机全链路通过；全套 51 项测试通过（offscreen 约 62 秒）；离线包交付：`D:\trash\Work\Innostar-ic\DTS\serial-debug-offline-py310-win_amd64.7z`（78.3MB，PySide6-Essentials+pyserial wheel 方案，py3.10 独立 venv 离线安装复验 + 51 项测试通过）。
- 已实现未验证：历史遗留的设备级 RX 应答往返（send 后确认设备回包）——现有 COM6 板持续输出 RRAM_TEST 日志，具备补验条件。
- 阻塞：无。
- 2026-10-19 复诊「自动检测并连接用不了」：代码未坏（20 项检测相关单测 + loop:// 桥/send 链路冒烟通过，`5519739` 后未再改动），根因是板子未接入——当前机器仅剩 COM4/COM5 两个蓝牙虚拟串口（BTHENUM，无 USB VID/PID，按设计被排除），上次验收用的 COM6 已不在系统；插回 USB 串口板后菜单 5 即恢复。本地配置仍为 COM6/115200，完好。
- 2026-10-19 新增「连接中波特率检测」：服务端乱码监视 + 自动重扫切换（默认被动，`AutoBaudProbe`/`--autobaud-probe` 开启主动探测）；控制动作 `serial.autobaud`/`autobaud.status`/`serial.autobaud.configure`，事件 `baud_scan`/`baud_changed`，终端注入「波特率已切换」提示；桥新增 `--autobaud*` 启动参数与 `autobaud` 在线检测子命令（exit 0/2/3/4/5/6）；菜单 10 增加方式 3「在线检测」并支持把新波特率写回本地配置；评分核心抽到 `scripts/serial_baud_scan.py` 供离线/在线共用（离线 CLI 行为不变）。agent 租约期间自动扫描暂停，手动触发不受影响。全套 66 项测试通过（+15）；loop:// 在线检测与 ps1 启动参数冒烟通过；实机波特率漂移验收待板子接回。
- 2026-10-20 修复「共享连接有时要断开再连接才能发数据」：根因是服务端 `_connection` 给控制（call）连接设了 30 秒 socket 超时，而 GUI 只在用户发送时才用这条连接——空闲超 30 秒服务端就静默关闭呼叫通道，订阅通道（RX 日志）还活着，会话仍显示已连接，之后每次发送都失败（仅一条 WARN），只有断开重连才恢复。修复两层：服务端 call 连接不再设空闲超时（`CONTROL_READ_TIMEOUT=None`，订阅/raw 仍各有 1 秒超时）；`serial_client.py`/`serial_service_client.py` 的 `Client.call` 遇传输层死亡自动重建呼叫通道并原样抛出本次错误（本次结果未知不自动重发，符合既有约定），ID 不匹配（通道错位）时同样重建。31 秒空闲复现脚本修复前红（设备收不到字节、会话假在线）修复后绿；新增 2 项回归测试（call 通道传输死亡后自愈：服务级 + GUI 端到端）；全套 72 项测试通过。注意：工作树还混有并行会话的 GUI 内联自动波特率未提交改动（`serial_gui_qt.py`/`serial_baud_scan.py`/`tests/test_ui_autobaud.py`），本次修复未提交，待用户决定提交切分。
- 2026-10-20 GUI 接入在线波特率检测（用户要求不开 CLI）：直连会话内置乱码监视（默认开，会话级「乱码自动重扫波特率」/「自动重扫允许主动探测」开关随会话持久化），中途换波特率自动切换并以 `SYS` 行提示；「日志设置」页与「更多」菜单新增「在线检测波特率」（被动/主动选择），直连走工作线程内 `scan_open_device`（扫描期间收发自然暂停），服务会话经 `serial.autobaud` + `baud_scan`/`baud_changed` 事件渲染；切换后同步会话波特率字段。注意 `SerialWorker` 的 `options` 是整个会话字典，会话级开关在 `options['options']`。全套 72 项测试通过（+4，tests/test_ui_autobaud.py；与连接修复的 2 项回归合并验证）。
- 2026-10-20 GUI 新增「共享串口桥」分组与一键停止：设置页按钮重排为 会话操作 → 波特率检测 → 「共享串口桥」分组（连接共享服务… / 终止 Agent 并接管 / 新按钮「停止桥并释放端口」，后两个按钮按会话类型显隐）；一键停止走 `ServiceStopWorker` 短连接：`status` 取 instance → 必要时 `agent.takeover` 收回租约 → `service.stop`，桥进程退出即释放串口，成功后自动退役本会话残留 worker（避免假在线）；未连接的服务会话也能停仍在运行的桥，失败（含服务不可达）写 ERROR 并置状态栏。新增 `tests/test_ui_service_controls.py` 5 项（分组显隐/确认释放/收回租约/取消不动作/不可达报错），全套 77 项测试通过。注意：`serial_gui_qt.py` 的本功能改动被并行会话的 `67255ca`（在线波特率检测）顺带带入且已推送，提交信息未覆盖本功能；本条目对应的补提交只含测试与文档。
- 2026-10-20 本对话收尾：服务端在线检测（`af63f9c`）、并行会话连接修复（`c6c3afa`，按用户切分决定代为提交）、GUI 接入（`67255ca`）均已推送；实机漂移验收待板子接回，交接见归档行。
- 下一步：用 RRAM_TEST 输出板补设备级往返、被动波特率检测与「在线检测（中途换波特率）」人工验收（先确认是否停板上的测试）；style token 改动同步上游 serial-gui 仓库。

## 对话归档

| 日期 / 对话 | 完成内容 | 交接 |
| --- | --- | --- |
| 2026-10-20 / GUI 在线波特率检测 + 连接中自动感知 | 复诊菜单 5「用不了」= 板子未接入；服务端乱码监视+自动重扫（`af63f9c`）；GUI 直连/服务会话接入检测按钮与自动感知（`67255ca`）；按用户切分代为提交并行会话连接修复（`c6c3afa`）；77 项测试通过；实机漂移验收待板子 | [GUI online baud detect](handoff-20261020-104200-gui-online-baud-detect.md) |
| 2026-10-14 / 离线打包（Qt 依赖入库） | 打包 serial-debug 离线 7z 到 DTS（Essentials wheel 方案，78.3MB，cp310-abi3 即 3.10+ 通用）；py3.10 独立 venv 离线安装与 51 项测试复验通过；未改源码 | [Offline package py310](handoff-20261014-145200-offline-package-py310.md) |
| 2026-10-14 / 日志降噪与串口工具修复、主动波特率检测 | 按键字节默认静默+显示开关、空行不渲染；菜单 5 与 GUI「自动检测串口」按钮均重做为优先连已接入 USB 口；修复 PS 5.1 配置编码损坏根因；新增主动波特率检测；COM6 实机验收；51 项测试通过 | [Log noise & baud detect](handoff-20261014-140402-log-noise-baud-detect.md) |
| 2026-10-14 / 工作流全链路实测与修复 | loop:// 与 COM6 实测控制器/桥/客户端/服务生命周期/agent 租约；修复 uv venv 安装文档、serial_gui.cmd .venv 优先、PS 5.1 JSON 传参说明、troubleshooting 陈旧参数；28 项测试通过（offscreen 27s） | （本次对话，未单独归档） |
| 2026-10-13 / 统一风格与可访问性改造 | 定档 Fluent 2 深色优先；token AA 修复、深色默认、Tab/状态栏错误/对话框行内校验修复；新增对比度与风格回归测试；测试基建提速 287s→27s | [Fluent2 style pass](handoff-20261014-110900-fluent2-style-pass.md) |
| 2026-10-13 / Qt 工作台替换薄客户端 | Qt 工作台加入服务会话与 agent 接管；skill 内置并重写集成测试；18 项测试通过 | （本次对话，未单独归档） |
| 2026-09-09 / Serial Phase 1 implementation | 完成服务、CLI、GUI、中文说明并推送；GUI 接管冒烟仍未完全通过 | [Serial Phase 1](handoff-20260909-160606-serial-phase1.md) |
