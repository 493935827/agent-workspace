# 交接记录：Serial Debug Phase 1

## 当前目标与范围

完成 GitHub Issue #1“共享 GUI、统一动作与 Agent 独占接管”的 Phase 1，实现服务端统一持有物理串口、结构化管理协议、兼容旧 TCP bridge、PySide6 GUI、Agent 独占/接管，以及 Windows 启动说明。

## 本次完成

- 在 `scripts/serial_service.py` 实现 loopback-only 共享串口服务、管理端口、事件广播、发送队列、任务状态、配置动作、设备释放/重连、异步日志、慢客户端隔离和 Agent token/heartbeat/takeover。
- 新增 `serial_protocol.py`、`serial_client.py`、`serial_control.py`、`serial_commands.py`、`serial_gui.py` 和 `serial_service_cli.py`。
- `shared_serial_bridge.py` 改为兼容旧 bridge/connect/send 的服务适配层；保留旧 CLI 和原始 TCP 行为。
- GUI 已加入中文标题、按钮、状态、错误提示，以及编码、换行和文本/HEX 选择。
- README 已补充中文安装、启动、连接、发送、独占、释放和常见问题说明。
- Windows requirements 加入 PySide6；新增 `windows/serial_gui.cmd`。

## 验证证据

- 服务测试 6 项通过：HEX、TX、接管取消、独占阻止、配置失败状态保留、输入校验。
- 旧 bridge/CLI 回归测试 4 项通过。
- 命令解析和增量 UTF-8 缓存测试 2 项通过。
- GUI 冒烟测试曾暴露接管异步状态刷新问题，服务端状态序列和 GUI 刷新已修过；最近一次单独 GUI 测试仍有失败，需继续定位后才可宣称 GUI 全部通过。
- Python 语法检查和 `git diff --check` 通过。

## 已提交与运行状态

- 远程 `origin/main` 已推送到提交 `e999970`（中文 GUI 和说明）；此前相关提交为 `c1fc350`、`60bcb76`、`ee16609`、`8f3a1c9`。
- 当前曾启动服务 PID `22264` 和 GUI PID `44096`；服务使用 raw `127.0.0.1:8888`、control `127.0.0.1:8889`，设备处于 released，未打开物理串口。继续工作前应重新检查 PID/端口，不要假设进程仍在。
- 配置默认 `COM10 @ 57600`，但当时系统检测到 COM3/4/16/20/5/34，没有 COM10，因此启动为 released service。

## 未完成与下一步

- 修复并重新运行 `tests/test_serial_gui.py` 的接管测试；重点检查事件队列中旧 state 事件覆盖 takeover 后的 human 状态，必要时使用事件 sequence 单调过滤或在接管后清空陈旧事件。
- 补 GUI 的数据位、停止位、校验位、xon/xoff、RTS/CTS、DSR/DTR 表单，以完整覆盖 Issue #1 GUI 参数要求。
- 补 partial write、write exception、raw TCP 独占拒绝后不重放、heartbeat timeout、日志故障和 100 KB/s 压力验证。
- 运行完整测试后，再按 `code-review` 对最终差异复审；如有修复则提交并推送。
- 真实硬件验收尚未执行：目标 COM、波特率、电平兼容、拔插恢复和 DTR/RTS 行为都需要人工确认。

## 相关入口

- 需求：`outputs/serial-debug-phase1-spec.md`（工作区快照）；权威 Issue：`https://github.com/493935827/serial-debug/issues/1`
- 使用说明：`README.md`
- 服务：`scripts/serial_service.py`
- GUI：`scripts/serial_gui.py`
- 测试：`tests/test_serial_service.py`、`tests/test_serial_gui.py`、`tests/test_serial_commands.py`、`tests/test_shared_serial_bridge.py`

## 建议技能

- 继续实现：`implement`。
- 测试优先修复 GUI：`tdd`。
- 最终差异审查：`code-review`。
- 完成代码修改后的提交/推送：`git-delivery`。
- 连接真实串口前：`serial-debug`，并阅读硬件安全说明。
