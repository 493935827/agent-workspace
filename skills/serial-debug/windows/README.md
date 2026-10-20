# 共享串口工具

这是一个适合 Windows 的中文串口工具。后台串口桥独占物理 COM 口，再把数据转发到本机 TCP 端口，让人工终端和自动化命令可以同时访问同一个串口。

交互终端直接使用成熟的 [pySerial miniterm](https://github.com/pyserial/pyserial/blob/master/serial/tools/miniterm.py)；外层保留本项目需要的中文菜单、手动开关、共享访问、自动检测、单条命令和日志功能。pySerial 使用 [BSD-3-Clause 许可证](https://github.com/pyserial/pyserial/blob/master/LICENSE.txt)，本项目通过依赖调用它，没有复制许可证不明的代码。

## 第一次使用

1. 双击 `serial_console.cmd`。
2. 如果端口和波特率都未知，直接选择 `5`：工具会优先选择已接入的 USB 串口（没有则等待插入）。
3. 波特率未知时，选择 `10` 自动检测当前端口的波特率（默认主动探测，也可选被动监听）；也可以选择 `8` 手动编辑本地配置。
4. 选择 `1` 启动串口桥，再选择 `2` 打开终端。
5. 如果已知端口和波特率，只需要选择 `5`，即可自动选中串口、启动串口桥并打开终端。
6. 终端中按 `Ctrl+C` 返回菜单；后台串口桥不会停止。

菜单窗口可以随时关闭；只要没有选择 `4`，后台串口桥就会继续运行。再次双击脚本即可查看状态、打开终端或停止它。

## 自动检测串口并连接

释放和自动连接是两个独立功能：

- 选项 `4`：只停止本工具的串口桥并释放当前 COM 口，不检测、不连接。
- 选项 `5`：自动检测串口并连接。优先选择当前已接入的 USB 串口（排除蓝牙）；没有已接入的 USB 串口时，转为等待最多 120 秒的新插入或重新插入。检测成功后保存端口、启动串口桥并自动打开 miniterm。
- 选项 `6`：只检测并保存下一次接入的串口，不启动串口桥。

选项 `5` 的行为细节：

- 目标 USB-UART 已经插入时，直接选中它，无需拔插。
- 没有任何已接入的 USB 串口时，先记录当前串口列表再等待最多 120 秒；把目标设备拔出再插入即可触发。
- 多个 USB 串口同时存在时，优先选择带 USB VID/PID 的非蓝牙端口，并提示检测到的候选数量。
- 串口桥正在运行时：目标与当前串口相同则直接打开终端；不同则询问确认后切换（当前会话会断开）。`-Action DetectConnect` 不询问，直接切换。
- 检测成功后，端口号写入 `serial_config.local.psd1`。
- 等待期间按 `Ctrl+C` 可以取消。

本地配置已加入 `.gitignore`，不会把个人 COM 号提交到 GitHub。

## 自动检测波特率

菜单选项 `10` 提供三种方式，并把可靠结果保存到本地配置：

- 方式 1/2 为**离线检测**：需要先用选项 `4` 释放本工具的串口桥，也要关闭其他直接占用该 COM 口的软件。
  - **主动探测（默认）**：每个候选波特率都会向设备发送回车探测字节，适合带提示符（如 `atom>>`）但不主动输出日志的设备。注意：检测会多次打开/关闭串口（部分开发板会因此复位），设备也会收到少量回车。
  - **被动监听**：只读取设备输出，不发送回车、`help` 或其他探测字符。设备必须在检测期间产生足够的文本输出；若固件仅在启动时打印日志，请在检测期间反复按开发板的复位键，注意复位会改变设备当前运行状态。被动检测会多次打开/关闭串口，但 DTR/RTS 保持为低，不会借此复位设备。
  - PowerShell 等价：`-Action AutoBaud`（主动，默认）、`-Action AutoBaud -Passive`（被动）；只保存配置，不启动串口桥。
- 方式 3 为**在线检测**：串口桥保持运行，不中断终端即可扫描候选波特率；检测成功后立即切换，所有终端会看到「波特率已从 X 切换为 Y」提示。命令行等价：

```powershell
python scripts\shared_serial_bridge.py autobaud --control 8889 --mode passive
python scripts\shared_serial_bridge.py autobaud --control 8889 --mode active   # 会发送回车探测
```

- 默认候选 `115200、57600、38400、19200、9600、230400、460800、921600`（外加当前波特率）；离线默认轮询 3 轮，在线默认 1 轮。
- 没有收到足够数据或多个结果过于接近时，工具会拒绝猜测，并保留原波特率。

### 连接中自动感知波特率变化

串口桥启动时默认开启乱码监视（`AutoBaudMonitor`）：设备中途更换波特率后，收到的字符会突然变成乱码；桥在滑动窗口内累计到足够乱码时会自动用候选波特率重扫，锁定后切换并提示。被动监视不发送任何数据；把 `AutoBaudProbe` 设为 `$true` 可允许自动重扫发送回车探测（适合中途换波特率但平时安静的设备，默认关闭）。代理（agent）占用串口期间自动扫描会暂停，手动触发的在线检测不受影响。若设备持续输出二进制数据（非文本日志），乱码监视可能误触发扫描；将 `AutoBaudMonitor` 设为 `$false` 可关闭。

在线扫描的候选与节奏由 `BaudCandidates`、`AutoBaudSeconds`、`AutoBaudRounds` 控制；离线检测使用 `BaudSampleSeconds` 和 `BaudRounds`。候选越多、监听越久，检测总时间越长。

Qt 工作台（`serial_gui.cmd`）无需命令行：直连会话默认开启「乱码自动重扫波特率」，设备中途换波特率会自动感知并切换，日志区打印 `SYS` 提示；「日志设置」页提供该开关、「自动重扫允许主动探测」复选框和「在线检测波特率」按钮（也可在主菜单「更多」里找到），服务会话同样支持手动在线检测。

## 配置说明

`serial_config.psd1` 是受 Git 管理的默认模板；自动检测或菜单选项 `8` 会创建 `serial_config.local.psd1`，工具优先读取本地配置。

- `Port`：串口号，例如 `COM10`。本地配置必须以 UTF-8（带 BOM）编码保存；用 ANSI 编码保存会使中文注释乱码，甚至把 `Port` 行吞进注释导致启动报“本地配置缺少 Port”。遇到该提示时选择菜单 `5` 重新检测，或菜单 `8` 修正即可。
- `Baud`：波特率，例如 `57600` 或 `115200`。
- `AutoBaudMonitor`：串口桥运行期间是否监视接收乱码并自动重扫波特率，默认 `$true`。
- `AutoBaudProbe`：是否允许自动重扫发送回车探测，默认 `$false`。
- `AutoBaudSeconds` / `AutoBaudRounds`：在线扫描每个候选的监听秒数与轮数（默认 `0.5` / `1`）。
- `LineEnding`：按 Enter 时发送的换行符。嵌入式 Shell 常用 `cr`；若命令不执行，可尝试 `crlf` 或 `lf`。
- `CharDelay`：逐字节发送间隔。较慢的 Shell 可以保留默认 `0.005`，高速可靠链路可设为 `0`。
- `TcpPort`：共享串口桥的本机 TCP 端口，默认 `8888`。
- `Python`：菜单和串口桥使用的解释器，默认 `python`。如果系统 Python 装不了 pyserial（例如 uv 管理的 `externally-managed` 环境），把它改成仓库内虚拟环境的完整路径，例如 `D:\path\to\serial-debug\.venv\Scripts\python.exe`。

默认监听 `127.0.0.1`，只有本机可以连接。工具不会主动切换 DTR/RTS，因此不会故意触发复位或 Boot 模式。

## 交互终端

菜单选项 `2` 通过 pySerial miniterm 连接后台串口桥：

- `Ctrl+C`：退出人工终端，后台串口桥继续运行。
- `Ctrl+T` 后按 `Ctrl+H`：查看 miniterm 快捷键。
- `Ctrl+T` 后按 `Ctrl+E`：切换本地回显。
- `Ctrl+T` 后按 `Ctrl+L`：切换换行方式。
- Enter 使用配置中的 `LineEnding`。
- 发送被拒绝（例如代理占用串口期间）时连接保持不断开，终端会显示 `[串口桥] 发送被拒绝：…` 提示，收回控制权后可直接继续发送。

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

- 如果 `pip install` 报 `externally-managed`（uv 管理的 Python），改用仓库内虚拟环境，并把本地配置的 `Python` 字段指向它：

```powershell
uv venv .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
```

- 如果提示 COM 口被占用，请先关闭其他直接打开该串口的软件。
- 拔插 USB 串口后，串口桥会每秒尝试重连。
- 如果会修改设备状态的命令发送中途断线，先从终端或日志确认设备状态，再决定是否重发。

## 硬件安全

连接前确认 USB-UART 与芯片 IO 电平兼容，并确认波特率、数据位、校验位和停止位。当前工具使用 pySerial 默认的 `8-N-1`、无流控配置。擦除、烧写、复位和进入 Bootloader 等动作仍需要明确确认后再执行。
