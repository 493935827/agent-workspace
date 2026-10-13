# 项目进度

最后更新：2026-10-13 12:10（Asia/Shanghai）

## 当前概况

- 目标 / 当前阶段：Issue #1 共享串口工具已完成 Phase 1 服务端；2026-10-13 人工 GUI 升级为 Qt 工作台。
- 工具切换（2026-10-13，用户授权）：删除 50 行服务薄客户端 `scripts/serial_gui.py`，改为内置 Qt 工作台（`serial_gui_qt.py` + `serial_gui_qt_prototype.py` + `serial_common.py` + `serial_service_client.py` + `qt-preview-tokens.json`，源自 serial-gui main `50fe938`）。工作台支持人工直连与共享服务会话（`更多 → 连接共享服务…`），并内置 agent 接管按钮。
- 跨仓库契约测试：`tests/test_serial_gui.py` 重写为「Qt 工作台 ↔ 真实 SerialService」集成测试（连接/发送/接管/关闭管理会话保留设备），PySide6 缺失时自动跳过；全套 18 项通过（PySide6 环境下，GUI 测试含真实服务链路）。
- 服务端、协议、桥、`serial_control.py` 均未改动；`windows/serial_gui.cmd` 指向新工作台。
- Qt 工作台自身的完整测试（含 FakeService、backspace 回显、服务会话）在 serial-gui 仓库维护（github.com/493935827/serial-gui）。
- 下一步：真实硬件验收仍待人工确认；skill 变更需同步规范仓库 github.com/493935827/serial-debug（本次已同步，见对话记录）。

## 对话归档

| 日期 / 对话 | 完成内容 | 交接 |
| --- | --- | --- |
| 2026-10-13 / Qt 工作台替换薄客户端 | Qt 工作台加入服务会话与 agent 接管；skill 内置并重写集成测试；18 项测试通过 | （本次对话，未单独归档） |
| 2026-09-09 / Serial Phase 1 implementation | 完成服务、CLI、GUI、中文说明并推送；GUI 接管冒烟仍未完全通过 | [Serial Phase 1](handoff-20260909-160606-serial-phase1.md) |
