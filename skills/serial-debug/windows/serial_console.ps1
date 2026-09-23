[CmdletBinding()]
param(
    [ValidateSet("Menu", "Start", "Stop", "Release", "Status", "Connect", "Send", "Ports", "AutoDetect", "DetectConnect", "AutoBaud")]
    [string]$Action = "Menu",
    [string]$Command
)

$ErrorActionPreference = "Stop"
$ToolDir = Split-Path -Parent $PSCommandPath
$DefaultConfigPath = Join-Path $ToolDir "serial_config.psd1"
$LocalConfigPath = Join-Path $ToolDir "serial_config.local.psd1"
$BridgePath = Join-Path $ToolDir "..\scripts\shared_serial_bridge.py"
$DetectorPath = Join-Path $ToolDir "detect_serial_port.py"
$BaudDetectorPath = Join-Path $ToolDir "detect_serial_baud.py"
$RuntimeDir = Join-Path $ToolDir ".runtime"
$PidPath = Join-Path $RuntimeDir "bridge.pid"
$DiagnosticLog = Join-Path $RuntimeDir "bridge_diagnostic.log"
$DiagnosticErrorLog = Join-Path $RuntimeDir "bridge_error.log"
$LogDir = Join-Path $ToolDir "logs"

function Get-ActiveConfigPath {
    if (Test-Path -LiteralPath $LocalConfigPath) { return $LocalConfigPath }
    return $DefaultConfigPath
}

function Get-SerialConfig {
    $ActiveConfigPath = Get-ActiveConfigPath
    if (-not (Test-Path -LiteralPath $ActiveConfigPath)) {
        throw "找不到配置文件：$ActiveConfigPath"
    }
    $ConfigText = Get-Content -LiteralPath $ActiveConfigPath -Raw -Encoding UTF8
    $Config = & ([scriptblock]::Create($ConfigText))
    if ($Config -isnot [System.Collections.IDictionary]) {
        throw "配置文件必须返回哈希表：$ActiveConfigPath"
    }
    return $Config
}

function Initialize-LocalConfig {
    if (-not (Test-Path -LiteralPath $LocalConfigPath)) {
        Copy-Item -LiteralPath $DefaultConfigPath -Destination $LocalConfigPath
    }
    return $LocalConfigPath
}

function Set-LocalSerialPort([string]$PortName) {
    $TargetPath = Initialize-LocalConfig
    $Content = Get-Content -LiteralPath $TargetPath -Raw
    $Pattern = '(?m)^(\s*Port\s*=\s*)"[^"]*"'
    if (-not [regex]::IsMatch($Content, $Pattern)) {
        throw "配置文件中找不到 Port 字段：$TargetPath"
    }
    $Replacement = '$1"' + $PortName + '"'
    $Updated = [regex]::Replace($Content, $Pattern, $Replacement, 1)
    # Windows PowerShell 5 需要 UTF-8 BOM，才能可靠解析中文注释。
    $Utf8Bom = New-Object System.Text.UTF8Encoding($true)
    [System.IO.File]::WriteAllText($TargetPath, $Updated, $Utf8Bom)
}

function Set-LocalBaud([int]$Baud) {
    $TargetPath = Initialize-LocalConfig
    $Content = Get-Content -LiteralPath $TargetPath -Raw
    $Pattern = '(?m)^(\s*Baud\s*=\s*)\d+'
    if (-not [regex]::IsMatch($Content, $Pattern)) {
        throw "配置文件中找不到 Baud 字段：$TargetPath"
    }
    $Updated = [regex]::Replace($Content, $Pattern, ('${1}' + [string]$Baud), 1)
    # Windows PowerShell 5 需要 UTF-8 BOM，才能可靠解析中文注释。
    $Utf8Bom = New-Object System.Text.UTF8Encoding($true)
    [System.IO.File]::WriteAllText($TargetPath, $Updated, $Utf8Bom)
}

function Get-BridgeProcess {
    if (-not (Test-Path -LiteralPath $PidPath)) { return $null }
    $SavedPid = [int](Get-Content -LiteralPath $PidPath -Raw)
    $ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $SavedPid" -ErrorAction SilentlyContinue
    if ($null -eq $ProcessInfo -or $ProcessInfo.CommandLine -notlike "*shared_serial_bridge.py*bridge*") {
        Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
        return $null
    }
    return $ProcessInfo
}

function Test-TcpEndpoint([string]$HostName, [int]$PortNumber) {
    $Client = [System.Net.Sockets.TcpClient]::new()
    try {
        $Task = $Client.ConnectAsync($HostName, $PortNumber)
        return $Task.Wait(500) -and $Client.Connected
    }
    catch { return $false }
    finally { $Client.Dispose() }
}

function Assert-PythonAndPySerial($Config) {
    & $Config.Python -c "import serial" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "缺少 pyserial。请执行：$($Config.Python) -m pip install -r `"$ToolDir\requirements.txt`""
    }
}

function Start-SerialBridge {
    $Config = Get-SerialConfig
    $Existing = Get-BridgeProcess
    if ($null -ne $Existing) {
        Write-Host "串口桥已经在运行（PID $($Existing.ProcessId)）。" -ForegroundColor Yellow
        return
    }
    Assert-PythonAndPySerial $Config
    New-Item -ItemType Directory -Path $RuntimeDir, $LogDir -Force | Out-Null
    Remove-Item -LiteralPath $DiagnosticLog, $DiagnosticErrorLog -Force -ErrorAction SilentlyContinue
    $SafePortName = ([string]$Config.Port) -replace '[^A-Za-z0-9._-]', '_'
    $SerialLog = Join-Path $LogDir ("serial_{0}_{1}.log" -f $SafePortName, (Get-Date -Format "yyyyMMdd_HHmmss"))
    $Arguments = @(
        $BridgePath, "bridge",
        "--port", [string]$Config.Port,
        "--baud", [string]$Config.Baud,
        "--host", [string]$Config.Host,
        "--tcp", [string]$Config.TcpPort,
        "--control", [string]$(if ($null -ne $Config.ControlPort) { $Config.ControlPort } else { 8889 }),
        "--chardelay", [string]$Config.CharDelay,
        "--log", $SerialLog
    )
    $Started = Start-Process -FilePath $Config.Python -ArgumentList $Arguments -WorkingDirectory $ToolDir `
        -WindowStyle Hidden -RedirectStandardOutput $DiagnosticLog `
        -RedirectStandardError $DiagnosticErrorLog -PassThru
    Set-Content -LiteralPath $PidPath -Value $Started.Id -Encoding ascii
    Start-Sleep -Milliseconds 900
    $Running = Get-BridgeProcess
    if ($null -eq $Running -or -not (Test-TcpEndpoint $Config.Host $Config.TcpPort)) {
        Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
        $Details = if (Test-Path -LiteralPath $DiagnosticErrorLog) {
            Get-Content -LiteralPath $DiagnosticErrorLog -Raw
        } else { "没有诊断输出。" }
        throw "串口桥启动失败，请检查 COM 口、波特率以及串口是否被其他软件占用。`n$Details"
    }
    Write-Host "已启动：$($Config.Port)，$($Config.Baud) 波特" -ForegroundColor Green
    Write-Host "共享地址：$($Config.Host):$($Config.TcpPort)"
    Write-Host "进程 PID：$($Running.ProcessId)"
    Write-Host "串口日志：$SerialLog"
}

function Stop-SerialBridge {
    $Running = Get-BridgeProcess
    if ($null -eq $Running) {
        Write-Host "串口桥当前没有运行。" -ForegroundColor Yellow
        return
    }
    Stop-Process -Id $Running.ProcessId -Force
    for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
        if ($null -eq (Get-Process -Id $Running.ProcessId -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 100
    }
    if ($null -ne (Get-Process -Id $Running.ProcessId -ErrorAction SilentlyContinue)) {
        throw "串口桥进程未能退出，COM 口可能仍被占用。"
    }
    Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
    Write-Host "已停止串口桥（PID $($Running.ProcessId)），COM 口已释放。" -ForegroundColor Green
}

function Show-SerialStatus {
    $Config = Get-SerialConfig
    $Running = Get-BridgeProcess
    $ConfigKind = if (Test-Path -LiteralPath $LocalConfigPath) { "本地配置" } else { "默认配置" }
    Write-Host "串口：     $($Config.Port)"
    Write-Host "波特率：   $($Config.Baud)"
    Write-Host "共享地址： $($Config.Host):$($Config.TcpPort)"
    Write-Host "换行方式： $($Config.LineEnding)"
    Write-Host "配置来源： $ConfigKind"
    if ($null -eq $Running) {
        Write-Host "运行状态： 已停止" -ForegroundColor Yellow
    } else {
        Write-Host "运行状态： 运行中（PID $($Running.ProcessId)）" -ForegroundColor Green
    }
}

function Show-SerialPorts {
    $Config = Get-SerialConfig
    Assert-PythonAndPySerial $Config
    Write-Host "当前检测到的串口：" -ForegroundColor Cyan
    $JsonLines = @(& $Config.Python $DetectorPath --list-json)
    if ($LASTEXITCODE -ne 0) { throw "读取串口列表失败。" }
    $Ports = @($JsonLines | ForEach-Object { $_ | ConvertFrom-Json })
    if ($Ports.Count -eq 0) {
        Write-Host "没有检测到串口。" -ForegroundColor Yellow
        return
    }
    foreach ($Port in $Ports) {
        Write-Host "- 串口：$($Port.device)" -ForegroundColor Green
        Write-Host "  说明：$($Port.description)"
        Write-Host "  硬件 ID：$($Port.hwid)"
        if ($null -ne $Port.vid -and $null -ne $Port.pid) {
            Write-Host ("  USB VID:PID：{0:X4}:{1:X4}" -f [int]$Port.vid, [int]$Port.pid)
        }
    }
}

function Find-NextSerialPort {
    $Config = Get-SerialConfig
    Assert-PythonAndPySerial $Config
    Write-Host "已记录当前串口列表。" -ForegroundColor Cyan
    Write-Host "请在 120 秒内插入 USB 串口；也可以先拔出目标串口，再重新插入。"
    Write-Host "等待期间按 Ctrl+C 可以取消。"
    $DetectedPort = & $Config.Python $DetectorPath --timeout 120
    $DetectorExitCode = $LASTEXITCODE
    if ($DetectorExitCode -eq 130) {
        Write-Host "已取消自动检测。" -ForegroundColor Yellow
        return
    }
    if ($DetectorExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($DetectedPort)) {
        throw "等待超时，没有检测到新接入的串口。"
    }
    $PortName = ([string]$DetectedPort).Trim()
    Set-LocalSerialPort $PortName
    Write-Host "已检测到串口：$PortName" -ForegroundColor Green
    Write-Host "已写入本地配置，下次启动串口桥时会自动使用该端口。" -ForegroundColor Green
    if ($null -ne (Get-BridgeProcess)) {
        Write-Host "当前串口桥仍使用原端口；请先停止再启动，使新配置生效。" -ForegroundColor Yellow
    }
    return $PortName
}

function Find-SerialBaud {
    $Config = Get-SerialConfig
    if ($null -ne (Get-BridgeProcess)) {
        throw "当前串口仍被本工具占用，请先选择菜单 4 释放当前 COM 口。"
    }
    if (Test-TcpEndpoint $Config.Host $Config.TcpPort) {
        throw "共享地址 $($Config.Host):$($Config.TcpPort) 已被占用，请先释放占用后再检测波特率。"
    }
    Assert-PythonAndPySerial $Config

    $DefaultBauds = @(115200, 57600, 38400, 19200, 9600, 230400, 460800, 921600)
    $BaudCandidates = if ($null -ne $Config.BaudCandidates) {
        @([int]$Config.Baud) + @($Config.BaudCandidates | ForEach-Object { [int]$_ }) | Select-Object -Unique
    } else {
        @([int]$Config.Baud) + $DefaultBauds | Select-Object -Unique
    }
    $SampleSeconds = if ($null -ne $Config.BaudSampleSeconds) { [double]$Config.BaudSampleSeconds } else { 0.8 }
    $Rounds = if ($null -ne $Config.BaudRounds) { [int]$Config.BaudRounds } else { 3 }

    Write-Host "正在被动检测 $($Config.Port) 的波特率，不会向设备发送数据。" -ForegroundColor Cyan
    Write-Host "请让设备持续输出日志；如果只在启动时输出，请在检测期间反复按开发板复位键。"
    Write-Host "候选波特率：$($BaudCandidates -join ', ')"
    $DetectedBaud = & $Config.Python $BaudDetectorPath --port $Config.Port `
        --bauds ($BaudCandidates -join ",") --seconds $SampleSeconds --rounds $Rounds
    $DetectorExitCode = $LASTEXITCODE
    if ($DetectorExitCode -eq 130) {
        Write-Host "已取消波特率检测。" -ForegroundColor Yellow
        return
    }
    if ($DetectorExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($DetectedBaud)) {
        if ($DetectorExitCode -eq 2) {
            throw "没有收到足够的有效输出。请让设备持续打印，或在检测期间反复复位后重试。"
        }
        if ($DetectorExitCode -eq 3) {
            throw "多个候选结果过于接近，无法可靠判断。请增加输出量后重试，或手动设置波特率。"
        }
        throw "波特率检测失败，请确认串口未被其他软件占用。"
    }
    $Baud = [int]([string]$DetectedBaud).Trim()
    Set-LocalBaud $Baud
    Write-Host "已检测到波特率：$Baud" -ForegroundColor Green
    Write-Host "已写入本地配置；需要选择菜单 1 启动串口桥。" -ForegroundColor Green
    return $Baud
}

function Detect-AndConnectNextSerialPort {
    $CurrentConfig = Get-SerialConfig
    if ($null -ne (Get-BridgeProcess)) {
        throw "当前串口仍被本工具占用，请先选择菜单 4 释放当前 COM 口。"
    }
    if (Test-TcpEndpoint $CurrentConfig.Host $CurrentConfig.TcpPort) {
        throw "共享地址 $($CurrentConfig.Host):$($CurrentConfig.TcpPort) 已被占用，请先释放占用后再连接。"
    }

    $DetectedPort = Find-NextSerialPort
    if ([string]::IsNullOrWhiteSpace($DetectedPort)) { return }

    Write-Host "正在连接新串口：$DetectedPort" -ForegroundColor Cyan
    Start-SerialBridge
    Open-SerialTerminal
}

function Edit-SerialConfig {
    $TargetPath = Initialize-LocalConfig
    Start-Process notepad.exe -ArgumentList $TargetPath -Wait
}

function Open-SerialTerminal {
    $Config = Get-SerialConfig
    if ($null -eq (Get-BridgeProcess)) { throw "串口桥已停止，请先启动。" }
    $SocketUrl = "socket://$($Config.Host):$($Config.TcpPort)"
    $MinitermEol = ([string]$Config.LineEnding).ToUpperInvariant()
    Write-Host "已使用 pySerial 官方 miniterm 打开交互终端。" -ForegroundColor Cyan
    Write-Host "按 Ctrl+C 返回菜单；按 Ctrl+T 后再按 Ctrl+H 查看终端快捷键。"
    Write-Host "退出终端不会停止后台串口桥。"
    & $Config.Python -m serial.tools.miniterm $SocketUrl $Config.Baud --quiet `
        --encoding $Config.Encoding --eol $MinitermEol --exit-char 3
}

function Send-SerialCommand([string]$Text) {
    $Config = Get-SerialConfig
    if ($null -eq (Get-BridgeProcess)) { throw "串口桥已停止，请先启动。" }
    & $Config.Python $BridgePath send $Text --host $Config.Host --tcp $Config.TcpPort `
        --encoding $Config.Encoding --line-ending $Config.LineEnding --newline
    if ($LASTEXITCODE -ne 0) {
        throw "命令结果不确定，请先检查交互终端或日志，再决定是否重发。"
    }
}

function Show-Menu {
    while ($true) {
        Clear-Host
        Write-Host "========== 共享串口工具 ==========" -ForegroundColor Cyan
        Show-SerialStatus
        Write-Host ""
        Write-Host "1. 启动串口桥"
        Write-Host "2. 打开交互终端"
        Write-Host "3. 发送单条命令"
        Write-Host "4. 停止串口桥并释放 COM 口"
        Write-Host "5. 自动检测下次接入的串口并连接"
        Write-Host "6. 只自动检测下次接入的串口"
        Write-Host "7. 查看当前串口"
        Write-Host "8. 编辑本地配置"
        Write-Host "9. 打开日志目录"
        Write-Host "10. 自动检测当前串口的波特率"
        Write-Host "0. 退出菜单（后台串口桥保持运行）"
        Write-Host ""
        $Choice = Read-Host "请选择"
        try {
            switch ($Choice) {
                "1" { Start-SerialBridge }
                "2" { Open-SerialTerminal }
                "3" { $Text = Read-Host "请输入命令"; Send-SerialCommand $Text }
                "4" { Stop-SerialBridge }
                "5" { Detect-AndConnectNextSerialPort }
                "6" { Find-NextSerialPort | Out-Null }
                "7" { Show-SerialPorts }
                "8" { Edit-SerialConfig }
                "9" {
                    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
                    Start-Process explorer.exe $LogDir
                }
                "10" { Find-SerialBaud | Out-Null }
                "0" { return }
                default { Write-Host "无法识别该选项。" -ForegroundColor Yellow }
            }
        }
        catch {
            Write-Host "错误：$($_.Exception.Message)" -ForegroundColor Red
        }
        if ($Choice -notin @("0", "2", "5", "8", "9")) {
            Write-Host ""
            Read-Host "按 Enter 继续" | Out-Null
        }
    }
}

switch ($Action) {
    "Start"      { Start-SerialBridge }
    "Stop"       { Stop-SerialBridge }
    "Release"    { Stop-SerialBridge }
    "Status"     { Show-SerialStatus }
    "Connect"    { Open-SerialTerminal }
    "Send"       {
        if ([string]::IsNullOrWhiteSpace($Command)) { throw "请通过 -Command 提供命令内容。" }
        Send-SerialCommand $Command
    }
    "Ports"      { Show-SerialPorts }
    "AutoDetect" { Find-NextSerialPort | Out-Null }
    "AutoBaud"   { Find-SerialBaud | Out-Null }
    "DetectConnect" { Detect-AndConnectNextSerialPort }
    default      { Show-Menu }
}
