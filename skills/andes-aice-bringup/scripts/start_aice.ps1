[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$ReleaseScript,

    [Parameter(Mandatory)]
    [string]$PythonExe,

    [Parameter(Mandatory)]
    [string]$IceRoot,

    [Parameter(Mandatory)]
    [string]$CygwinBash,

    [int]$GdbPort = 9901,
    [int]$Config = 14
)

$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') {
    throw 'Andes AICE bring-up currently supports Windows only.'
}

foreach ($requiredPath in @($ReleaseScript, $PythonExe, $IceRoot, $CygwinBash)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required path does not exist: $requiredPath"
    }
}

$mi00 = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
    Where-Object { $_.InstanceId -like 'USB\VID_0403&PID_6010&MI_00*' } |
    Select-Object -First 1
$mi01 = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
    Where-Object { $_.InstanceId -like 'USB\VID_0403&PID_6010&MI_01*' } |
    Select-Object -First 1

if (-not $mi00 -or -not $mi01) {
    throw 'Both AICE FTDI interfaces (MI_00 and MI_01) must be connected.'
}

$mi00Service = (Get-PnpDeviceProperty -InstanceId $mi00.InstanceId -KeyName 'DEVPKEY_Device_Service').Data
$mi01Service = (Get-PnpDeviceProperty -InstanceId $mi01.InstanceId -KeyName 'DEVPKEY_Device_Service').Data
if ($mi00Service -ne 'libusbK' -or $mi01Service -ne 'FTDIBUS') {
    throw "Wrong driver split: MI_00=$mi00Service, MI_01=$mi01Service. Expected libusbK/FTDIBUS."
}

Write-Host '[1/5] Stopping existing ICEman/OpenOCD processes...'
Get-Process -Name 'ICEman', 'openocd' -ErrorAction SilentlyContinue |
    Stop-Process -Force
Start-Sleep -Milliseconds 500

Write-Host '[2/5] Restarting the AICE USB parent device...'
$aiceParent = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
    Where-Object {
        $_.InstanceId.StartsWith(
            'USB\VID_0403&PID_6010\',
            [System.StringComparison]::OrdinalIgnoreCase
        )
    } |
    Select-Object -First 1
if (-not $aiceParent) {
    throw 'AICE USB parent VID_0403&PID_6010 is not connected.'
}

$restartArgs = @('/restart-device', ('"' + $aiceParent.InstanceId + '"'))
$restartProcess = Start-Process `
    -FilePath (Join-Path $env:SystemRoot 'System32\pnputil.exe') `
    -ArgumentList $restartArgs `
    -Verb RunAs `
    -Wait `
    -PassThru
if ($restartProcess.ExitCode -ne 0) {
    throw "AICE USB restart failed with exit code $($restartProcess.ExitCode)."
}

Write-Host '[3/5] Waiting for both FTDI interfaces...'
$deadline = [DateTime]::UtcNow.AddSeconds(15)
do {
    $mi00 = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
        Where-Object { $_.InstanceId -like 'USB\VID_0403&PID_6010&MI_00*' } |
        Select-Object -First 1
    $mi01 = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
        Where-Object { $_.InstanceId -like 'USB\VID_0403&PID_6010&MI_01*' } |
        Select-Object -First 1
    if ($mi00.Status -eq 'OK' -and $mi01.Status -eq 'OK') {
        break
    }
    Start-Sleep -Milliseconds 500
} while ([DateTime]::UtcNow -lt $deadline)
if ($mi00.Status -ne 'OK' -or $mi01.Status -ne 'OK') {
    throw 'AICE USB interfaces did not recover within 15 seconds.'
}

Write-Host '[4/5] Releasing the target CPU before ICEman...'
$releaseOutput = & $PythonExe $ReleaseScript 2>&1
$releaseExitCode = $LASTEXITCODE
$releaseOutput | ForEach-Object { Write-Host $_ }
if ($releaseExitCode -ne 0) {
    throw "CPU-release script failed with exit code $releaseExitCode."
}
if (($releaseOutput | Out-String) -match '(?i)0xffffffff') {
    throw 'CPU-release reads are 0xFFFFFFFF; ICEman was not started.'
}

$cygpathExe = Join-Path (Split-Path -Parent $CygwinBash) 'cygpath.exe'
if (-not (Test-Path -LiteralPath $cygpathExe)) {
    throw "Cygwin cygpath.exe is missing beside bash.exe: $cygpathExe"
}
$cygwinIceRoot = (& $cygpathExe -u -a $IceRoot).Trim()
if (-not $cygwinIceRoot) {
    throw "Could not translate the ICE path for Cygwin: $IceRoot"
}

Write-Host '[5/5] Starting ICEman; keep this terminal open...'
$iceCommand = "cd '$cygwinIceRoot' && ./ICEman.exe -Z v5 -p $GdbPort -X -c $Config"
& $CygwinBash -lc $iceCommand
exit $LASTEXITCODE
