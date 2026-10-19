# 项目进度

最后更新：2026-10-19 18:12（Asia/Shanghai）

## 当前概况

- 目标 / 当前阶段：serial-debug skill 全链路（服务端 + Qt 工作台 + Windows 控制器 + bridge/客户端）持续迭代；Issue #1 Phase 1 已完成，进入实机验收与打磨期。
- 已完成并验证：Windows 控制器全工作流（含 uv shim 场景）；Qt 工作台 Fluent 2 深色风格与可访问性改造；GUI 日志降噪（按键字节默认静默 + 「显示按键字节」开关，`2ed0ad6`/`cb4af8d`）；菜单 5「自动检测串口并连接」重做并修复配置编码损坏根因、主动波特率检测（`e6989e5`）；GUI「自动检测串口」按钮重做（唯一已接入 USB 口直连、多候选预选列表、无 USB 才等待）；COM6 实机全链路通过；全套 51 项测试通过（offscreen 约 62 秒）；离线包交付：`D:\trash\Work\Innostar-ic\DTS\serial-debug-offline-py310-win_amd64.7z`（78.3MB，PySide6-Essentials+pyserial wheel 方案，py3.10 独立 venv 离线安装复验 + 51 项测试通过）。
- 已实现未验证：历史遗留的设备级 RX 应答往返（send 后确认设备回包）——现有 COM6 板持续输出 RRAM_TEST 日志，具备补验条件。
- 阻塞：无。
- 2026-10-19 复诊「自动检测并连接用不了」：代码未坏（20 项检测相关单测 + loop:// 桥/send 链路冒烟通过，`5519739` 后未再改动），根因是板子未接入——当前机器仅剩 COM4/COM5 两个蓝牙虚拟串口（BTHENUM，无 USB VID/PID，按设计被排除），上次验收用的 COM6 已不在系统；插回 USB 串口板后菜单 5 即恢复。本地配置仍为 COM6/115200，完好。
- 2026-10-19 新增「连接中波特率检测」：服务端乱码监视 + 自动重扫切换（默认被动，`AutoBaudProbe`/`--autobaud-probe` 开启主动探测）；控制动作 `serial.autobaud`/`autobaud.status`/`serial.autobaud.configure`，事件 `baud_scan`/`baud_changed`，终端注入「波特率已切换」提示；桥新增 `--autobaud*` 启动参数与 `autobaud` 在线检测子命令（exit 0/2/3/4/5/6）；菜单 10 增加方式 3「在线检测」并支持把新波特率写回本地配置；评分核心抽到 `scripts/serial_baud_scan.py` 供离线/在线共用（离线 CLI 行为不变）。agent 租约期间自动扫描暂停，手动触发不受影响。全套 66 项测试通过（+15）；loop:// 在线检测与 ps1 启动参数冒烟通过；实机波特率漂移验收待板子接回。
- 下一步：用 RRAM_TEST 输出板补设备级往返、被动波特率检测与「在线检测（中途换波特率）」人工验收（先确认是否停板上的测试）；style token 改动同步上游 serial-gui 仓库；GUI 侧如需「在线波特率检测」按钮可直接调用 `serial.autobaud` 控制动作并订阅 `baud_changed`/`baud_scan` 事件（备忘，未被要求）。

## 对话归档

| 日期 / 对话 | 完成内容 | 交接 |
| --- | --- | --- |
| 2026-10-14 / 离线打包（Qt 依赖入库） | 打包 serial-debug 离线 7z 到 DTS（Essentials wheel 方案，78.3MB，cp310-abi3 即 3.10+ 通用）；py3.10 独立 venv 离线安装与 51 项测试复验通过；未改源码 | [Offline package py310](handoff-20261014-145200-offline-package-py310.md) |
| 2026-10-14 / 日志降噪与串口工具修复、主动波特率检测 | 按键字节默认静默+显示开关、空行不渲染；菜单 5 与 GUI「自动检测串口」按钮均重做为优先连已接入 USB 口；修复 PS 5.1 配置编码损坏根因；新增主动波特率检测；COM6 实机验收；51 项测试通过 | [Log noise & baud detect](handoff-20261014-140402-log-noise-baud-detect.md) |
| 2026-10-14 / 工作流全链路实测与修复 | loop:// 与 COM6 实测控制器/桥/客户端/服务生命周期/agent 租约；修复 uv venv 安装文档、serial_gui.cmd .venv 优先、PS 5.1 JSON 传参说明、troubleshooting 陈旧参数；28 项测试通过（offscreen 27s） | （本次对话，未单独归档） |
| 2026-10-13 / 统一风格与可访问性改造 | 定档 Fluent 2 深色优先；token AA 修复、深色默认、Tab/状态栏错误/对话框行内校验修复；新增对比度与风格回归测试；测试基建提速 287s→27s | [Fluent2 style pass](handoff-20261014-110900-fluent2-style-pass.md) |
| 2026-10-13 / Qt 工作台替换薄客户端 | Qt 工作台加入服务会话与 agent 接管；skill 内置并重写集成测试；18 项测试通过 | （本次对话，未单独归档） |
| 2026-09-09 / Serial Phase 1 implementation | 完成服务、CLI、GUI、中文说明并推送；GUI 接管冒烟仍未完全通过 | [Serial Phase 1](handoff-20260909-160606-serial-phase1.md) |
