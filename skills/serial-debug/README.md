# Shared Serial Debug

## 中文使用说明

### 1. 安装

在 PowerShell 进入仓库目录，执行：

```powershell
python -m pip install -r windows/requirements.txt
```

### 2. 启动

推荐先启动共享服务，再启动中文 GUI：

```powershell
python scripts/serial_service_cli.py --tcp 8888 --control 8889
python scripts/serial_gui.py
```

也可以双击 `windows/serial_gui.cmd` 启动 GUI。GUI 关闭时只断开 GUI 会话，不会停止后台服务。

### 3. 连接设备

在 GUI 的“串口”填写目标 COM 号，在“波特率”填写设备速率，点击“连接设备”。高级配置和设备列表可通过命令栏调用：

```text
serial.list
serial.open {"port":"COM5","baudrate":57600}
serial.configure {"baudrate":57600,"bytesize":8,"stopbits":1,"parity":"N","xonxoff":false,"rtscts":false,"dsrdtr":false}
```

“释放设备”会关闭物理串口并停止自动重连，但保留服务和其他观察客户端。

### 4. 发送与查看

选择“编码”（UTF-8 或 ASCII）、“换行”（无、CR、LF、CRLF）和“发送模式”（文本或 HEX），在命令栏输入 JSON 命令后按 Enter，或点击“发送”：

```text
send {"data":"help","encoding":"utf-8","newline":"cr"}
send.hex {"data":"AA 55 01 02 FF"}
```

HEX 必须由完整的两位十六进制字节组成。接收数据显示 `[RX]`，实际写入数据显示 `[TX]`。TX 表示驱动已接受字节，不表示设备已经执行命令。

### 5. Agent 独占与人工接管

Agent 先调用 `agent.acquire` 获得凭证，并按返回的心跳周期调用 `agent.heartbeat`。独占期间其他客户端不能发送、修改配置或开关设备，但仍可查看状态和 RX/TX。GUI 点击“终止 Agent 并接管”后，排队任务会取消，旧凭证失效，服务确认停止旧写入后才恢复人工控制。

### 6. 常见问题

- `设备：已释放`：服务正常运行，但没有打开物理串口；先选择正确 COM 号并点击“连接设备”。
- `找不到 COM 口`：执行 `python windows/detect_serial_port.py --list-json` 查看系统实际端口；不要盲目选择蓝牙串口。
- 发送结果为 `unknown`：只能先观察终端输出和日志，不能自动重发，因为设备可能已经收到部分数据。
- 管理端口 `8889` 被占用：停止旧的 managed service，或为服务和 GUI 同时指定另一组端口。

This repository owns one physical serial port in a background service. Legacy `bridge`, `connect`, `send`, and `socket://` clients continue to use the raw TCP endpoint. New GUI and machine clients use the newline-delimited JSON control endpoint.

Install on Windows with `python -m pip install -r windows/requirements.txt`. Start the managed service with `python scripts/serial_service_cli.py --port COM10 --baud 115200`, then run `python scripts/serial_gui.py` or invoke an action with `python scripts/serial_control.py status --control 8889`.

The service binds loopback only. Raw TCP defaults to port 8888 and management defaults to 8889. The management protocol is version 1, uses one JSON object per line, rejects messages over 256 KiB and sends over 64 KiB, and represents binary data as base64 in RX/TX events. `send.hex` accepts complete byte pairs such as `AA 55 01 02 FF`; malformed pairs are rejected before any write. Text uses UTF-8 by default and supports ASCII plus `none`, `cr`, `lf`, or `crlf` line endings.

An Agent must call `agent.acquire`, heartbeat at the returned interval, and pass its lease token to every mutating action. Heartbeat expiry, normal release, and `agent.takeover` invalidate the old token and cancel queued work. Takeover waits for an active byte write to stop before returning human control. A send result of `written` means the driver accepted the bytes; it does not mean the device executed the command. `unknown` must not be retried automatically.

Closing the GUI closes only its management session. `serial.close` releases the device while leaving the service and raw clients alive; it also disables automatic reconnect until `serial.open` or `serial.reconnect`. Logs are asynchronous and bounded; a log error or dropped client event is exposed in `status` and does not stop RX.

The Windows menu remains in `windows/serial_console.ps1`; `windows/serial_gui.cmd` starts the GUI. `serial_config.local.psd1` overrides the complete default configuration and is not committed. Hardware round trips still require the manual acceptance checklist: open the selected COM port, verify parameters and line endings, observe raw RX/TX, unplug and reinsert the board, release the device, and confirm control-line behavior.
