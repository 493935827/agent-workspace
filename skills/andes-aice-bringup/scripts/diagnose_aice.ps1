[CmdletBinding()]
param(
    [string]$IceRoot
)

$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') {
    throw 'Andes AICE diagnostics currently support Windows only.'
}

$devices = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
    Where-Object {
        $_.InstanceId -like 'USB\VID_0403&PID_6010*' -or
        $_.InstanceId -like 'USB\VID_0000&PID_0003*'
    } |
    ForEach-Object {
        [pscustomobject]@{
            status = $_.Status
            class = $_.Class
            name = $_.FriendlyName
            instance_id = $_.InstanceId
            problem_code = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_ProblemCode' -ErrorAction SilentlyContinue).Data
            service = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_Service' -ErrorAction SilentlyContinue).Data
            driver_inf = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_DriverInfPath' -ErrorAction SilentlyContinue).Data
            driver_version = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_DriverVersion' -ErrorAction SilentlyContinue).Data
            parent = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_Parent' -ErrorAction SilentlyContinue).Data
        }
    }

$processes = Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessName -match '^(ICEman|openocd)$' } |
    ForEach-Object {
        [pscustomobject]@{
            name = $_.ProcessName
            pid = $_.Id
            path = $_.Path
            started = $_.StartTime
        }
    }

$ports = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 2354, 4444, 6666, 9901 } |
    ForEach-Object {
        [pscustomobject]@{
            address = $_.LocalAddress
            port = $_.LocalPort
            pid = $_.OwningProcess
        }
    }

$iceFiles = $null
if ($IceRoot) {
    $iceFiles = [pscustomobject]@{
        root = $IceRoot
        iceman = Test-Path -LiteralPath (Join-Path $IceRoot 'ICEman.exe')
        jtagkey_config = Test-Path -LiteralPath (Join-Path $IceRoot 'interface\jtagkey.cfg')
        ftdi_driver_inf = Test-Path -LiteralPath (Join-Path $IceRoot 'libusb-AICE-driver\FTDI_USB_device.inf')
        debug0_log = Test-Path -LiteralPath (Join-Path $IceRoot 'iceman_debug0.log')
        debug1_log = Test-Path -LiteralPath (Join-Path $IceRoot 'iceman_debug1.log')
    }
}

[pscustomobject]@{
    timestamp = [DateTime]::Now.ToString('o')
    devices = @($devices)
    processes = @($processes)
    listeners = @($ports)
    ice_files = $iceFiles
} | ConvertTo-Json -Depth 6
