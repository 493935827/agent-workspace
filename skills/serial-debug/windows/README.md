# 共享串口工具

这是一个适合 Windows 的中文串口工具。后台串口桥独占物理 COM 口，再把数据转发到本机 TCP 端口，让人工终端和自动化命令可以同时访问同一个串口。

交互终端直接使用成熟的 [pySerial miniterm](https://github.com/pyserial/pyserial/blob/master/serial/tools/miniterm.py)；外层保留本项目需要的中文菜单、手动开关、共享访问、自动检测、单条命令和日志功能。pySerial 使用 [BSD-3-Clause 许可证](https://github.com/pyserial/pyserial/blob/master/LICENSE.txt)，本项目通过依赖调用它，没有复制许可证不明的代码。

## 第一次使用

1. 双击 `serial_console.cmd`。
2. 如果当前串口桥正在运行，先选择 `4`，只释放当前 COM 口。
3. 如果端口和波特率都未知，选择 `6` 检测并保存端口，但先不连接。
4. 选择 `10` 自动检测当前端口的波特率；也可以选择 `8` 手动编辑本地配置。
5. 选择 `1` 启动串口桥，再选择 `2` 打开终端。
6. 如果已知波特率，只需要选择 `5`，即可检测端口、启动串口桥并打开终端。
7. 终端中按 `Ctrl+C` 返回菜单；后台串口桥不会停止。

菜单窗口可以随时关闭；只要没有选择 `4`，后台串口桥就会继续运行。再次双击脚本即可查看状态、打开终端或停止它。

## 自动检测下一次接入的串口

释放和自动连接是两个独立功能：

- 选项 `4`：只停止本工具的串口桥并释放当前 COM 口，不检测、不连接。
- 选项 `5`：检测下一次接入，保存新端口，启动串口桥并自动打开 miniterm；如果旧串口尚未释放，会提示先执行选项 `4`。
- 选项 `6`：只检测并保存下一次接入的串口，不启动串口桥。

检测过程会先记录当前串口列表，再等待最多 120 秒：

- 目标 USB-UART 尚未插入时，直接选择该功能，然后插入设备。
- 目标设备已经插入时，选择该功能后将它拔出再插入。
- 如果一次出现多个端口，优先选择带 USB VID/PID 的非蓝牙端口。
- 检测成功后，端口号写入 `serial_config.local.psd1`。
- 如果串口桥正在运行，新端口会在下一次停止并重新启动后生效。
- 等待期间按 `Ctrl+C` 可以取消。

本地配置已加入 `.gitignore`，不会把个人 COM 号提交到 GitHub。

## 自动检测波特率

菜单选项 `10` 会对当前配置的 COM 口依次尝试常见波特率，并把可靠结果保存到本地配置。PowerShell 中可使用 `-Action AutoBaud`。

- 检测前必须先用选项 `4` 释放本工具的串口桥，也要关闭其他直接占用该 COM 口的软件。
- 检测是被动的：只读取设备输出，不发送回车、`help` 或其他探测字符，也不主动切换 DTR/RTS。
- 设备必须在检测期间产生足够的文本输出。若固件仅在启动时打印日志，请在检测期间反复按开发板的复位键；注意复位会改变设备当前运行状态。
- 默认检测 `115200、57600、38400、19200、9600、230400、460800、921600`，共轮询 3 轮。
- 没有收到足够数据或多个结果过于接近时，工具会拒绝猜测，并保留原波特率。
- 检测成功后只保存配置，不自动启动串口桥；选择菜单 `1` 后才会占用串口。

配置中的 `BaudCandidates`、`BaudSampleSeconds` 和 `BaudRounds` 可调整候选范围、单次监听时间和轮数。候选越多、监听越久，检测总时间越长。

## 配置说明

`serial_config.psd1` 是受 Git 管理的默认模板；自动检测或菜单选项 `8` 会创建 `serial_config.local.psd1`，工具优先读取本地配置。

- `Port`：串口号，例如 `COM10`。
- `Baud`：波特率，例如 `57600` 或 `115200`。
- `LineEnding`：按 Enter 时发送的换行符。嵌入式 Shell 常用 `cr`；若命令不执行，可尝试 `crlf` 或 `lf`。
- `CharDelay`：逐字节发送间隔。较慢的 Shell 可以保留默认 `0.005`，高速可靠链路可设为 `0`。
- `TcpPort`：共享串口桥的本机 TCP 端口，默认 `8888`。

默认监听 `127.0.0.1`，只有本机可以连接。工具不会主动切换 DTR/RTS，因此不会故意触发复位或 Boot 模式。

## 交互终端

菜单选项 `2` 通过 pySerial miniterm 连接后台串口桥：

- `Ctrl+C`：退出人工终端，后台串口桥继续运行。
- `Ctrl+T` 后按 `Ctrl+H`：查看 miniterm 快捷键。
- `Ctrl+T` 后按 `Ctrl+E`：切换本地回显。
- `Ctrl+T` 后按 `Ctrl+L`：切换换行方式。
- Enter 使用配置中的 `LineEnding`。

## PowerShell 命令

除了双击菜单，也可以执行：

```powershell
.\serial_console.ps1 -Action Release
.\serial_console.ps1 -Action DetectConnect
.\serial_console.ps1 -Action AutoDetect
.\serial_console.ps1 -Action AutoBaud
.\serial_console.ps1 -Action Start
.\serial_console.ps1 -Action Status
.\serial_console.ps1 -Action Connect
.\serial_console.ps1 -Action Send -Command "help"
.\serial_console.ps1 -Action Ports
.\serial_console.ps1 -Action Stop
```

## 日志和故障排查

- 串口收到的原始数据保存在 `logs` 目录。
- 串口桥启动诊断保存在 `.runtime` 目录。
- 如果提示找不到 `serial` 模块，执行：

```powershell
python -m pip install -r requirements.txt
```

- 如果提示 COM 口被占用，请先关闭其他直接打开该串口的软件。
- 拔插 USB 串口后，串口桥会每秒尝试重连。
- 如果会修改设备状态的命令发送中途断线，先从终端或日志确认设备状态，再决定是否重发。

## 硬件安全

连接前确认 USB-UART 与芯片 IO 电平兼容，并确认波特率、数据位、校验位和停止位。当前工具使用 pySerial 默认的 `8-N-1`、无流控配置。擦除、烧写、复位和进入 Bootloader 等动作仍需要明确确认后再执行。
