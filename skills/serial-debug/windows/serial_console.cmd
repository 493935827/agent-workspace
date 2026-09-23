@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0serial_console.ps1"
if errorlevel 1 (
  echo.
  echo 串口工具异常退出，请查看上面的错误信息。
  pause
)
