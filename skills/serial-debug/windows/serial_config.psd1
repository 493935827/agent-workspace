@{
    # 默认配置。自动检测或手动编辑后，会创建优先级更高的 serial_config.local.psd1。
    # 串口号示例：COM10。
    Port       = "COM10"
    Baud       = 57600

    # 被动波特率检测参数。检测不会发送串口数据；设备需要在检测期间输出日志。
    BaudCandidates   = @(115200, 57600, 38400, 19200, 9600, 230400, 460800, 921600)
    BaudSampleSeconds = 0.8   # 每个候选每轮监听秒数
    BaudRounds        = 3     # 轮询所有候选的次数
    # 在线波特率检测（串口桥运行期间）：监视接收乱码并自动重扫、切换波特率。
    AutoBaudMonitor = $true     # 随串口桥启动开启乱码监视（被动，不发送数据）
    AutoBaudProbe   = $false    # $true 时允许自动重扫发送回车探测（默认关闭）
    AutoBaudSeconds = 0.5       # 在线扫描每个候选波特率的监听秒数
    AutoBaudRounds  = 1         # 在线扫描轮数

    # 共享串口桥使用的本机 TCP 地址。除非明确需要局域网访问，否则保持 127.0.0.1。
    Host       = "127.0.0.1"
    TcpPort    = 8888
    ControlPort = 8889

    # 常见嵌入式 Shell 按 Enter 时使用 CR；也可设置为 lf 或 crlf。
    LineEnding = "cr"
    Encoding   = "utf-8"
    CharDelay  = 0.005      # 每个发送字节之间的延迟，单位为秒
    Python     = "python"
}
