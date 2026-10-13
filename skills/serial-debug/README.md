# Shared Serial Debug

## 中文使用说明

### 1. 安装

在 PowerShell 进入仓库目录，执行：

```powershell
python -m pip install -r windows/requirements.txt
```

### 2. 启动

推荐先启动共享服务，再启动中文 Qt 工作台：

```powershell
python scripts/serial_service_cli.py --tcp 8888 --control 8889
python scripts/serial_gui_qt.py
```

也可以双击 `windows/serial_gui.cmd` 启动工作台。工作台关闭只断开自己的会话，不会停止后台服务。

### 3. 连接设备

工作台有两种用法：

- **人工直连**：只做人工调试时，在会话中直接选择串口与波特率连接；工作台进程独占该 COM 口。
- **共享服务**：人工与 Agent 共用同一串口时，启动共享服务（`serial_service_cli.py`），再在工作台菜单选择「更多 → 连接共享服务…」，填写服务地址（默认 `127.0.0.1`）、控制端口（默认 `8889`）、目标串口和波特率。服务独占物理串口，工作台作为观察/控制客户端接入；这与 miniterm、`serial_control.py` 使用同一个中间层。

同一 COM 口只能被一方持有：共享服务已连接设备时，不要再直连同一串口；反之直连时也无法启动共享服务。

### 4. 发送与查看

工作台支持编码（UTF-8/GBK）、换行（CR/LF/CRLF）、文本与 HEX 显示、多串口标签、逐行宏、ANSI 渲染、持续日志、条件提醒和搜索。接收显示 `[RX]`，实际写入显示 `[TX]`；TX 表示驱动已接受字节，不表示设备已经执行命令。

共享服务会话中，Agent 通过服务发送的命令会以 `[TX]` 显示在人工端，双方看到同一份控制台内容。

### 5. Agent 独占与人工接管

Agent 通过 `agent.acquire` 获得凭证并按返回周期心跳。独占期间其他客户端不能发送或修改配置，但仍可查看状态和 RX/TX。共享服务会话下，工作台状态栏会显示当前控制权；Agent 占用时，设置页的「终止 Agent 并接管」按钮可用，点击后排队任务取消、旧凭证失效，服务确认停止旧写入后恢复人工控制。发送结果为未知时不得自动重发。

### 6. 常见问题

- `设备：已释放`：服务正常运行，但没有打开物理串口；先选择正确 COM 号并连接。
- `找不到 COM 口`：执行 `python windows/detect_serial_port.py --list-json` 查看系统实际端口；不要盲目选择蓝牙串口。
- 发送结果为 `unknown`：只能先观察终端输出和日志，不能自动重发，因为设备可能已经收到部分数据。
- 管理端口 `8889` 被占用：停止旧的 managed service，或为服务和会话同时指定另一组端口。

This repository owns one physical serial port in a background service. Legacy `bridge`, `connect`, `send`, and `socket://` clients continue to use the raw TCP endpoint. The Qt workbench (`scripts/serial_gui_qt.py`) is the human-facing console: it can drive a COM port directly for manual debugging, or attach to the managed service as a shared client with the same protocol as `scripts/serial_service_client.py` (protocol version 1).

Install on Windows with `python -m pip install -r windows/requirements.txt`. Start the managed service with `python scripts/serial_service_cli.py --port COM10 --baud 115200`, then run `python scripts/serial_gui_qt.py` and connect through「更多 → 连接共享服务…」, or invoke an action with `python scripts/serial_control.py status --control 8889`.

The service binds loopback only. Raw TCP defaults to port 8888 and management defaults to 8889. The management protocol is version 1, uses one JSON object per line, rejects messages over 256 KiB and sends over 64 KiB, and represents binary data as base64 in RX/TX events. `send.hex` accepts complete byte pairs such as `AA 55 01 02 FF`; malformed pairs are rejected before any write. Text uses UTF-8 by default and supports ASCII plus `none`, `cr`, `lf`, or `crlf` line endings.

An Agent must call `agent.acquire`, heartbeat at the returned interval, and pass its lease token to every mutating action. Heartbeat expiry, normal release, and `agent.takeover` invalidate the old token and cancel queued work. Takeover waits for an active byte write to stop before returning human control. A send result of `written` means the driver accepted the bytes; it does not mean the device executed the command. `unknown` must not be retried automatically.

Closing the workbench closes only its management session. `serial.close` releases the device while leaving the service and raw clients alive; it also disables automatic reconnect until `serial.open` or `serial.reconnect`. Logs are asynchronous and bounded; a log error or dropped client event is exposed in `status` and does not stop RX.

The Windows menu remains in `windows/serial_console.ps1`; `windows/serial_gui.cmd` starts the workbench. `serial_config.local.psd1` overrides the complete default configuration and is not committed. Hardware round trips still require the manual acceptance checklist: open the selected COM port, verify parameters and line endings, observe raw RX/TX, unplug and reinsert the board, release the device, and confirm control-line behavior.
