@echo off
setlocal
set "TOOL_DIR=%~dp0"
set "PYTHON=python"
rem 优先使用仓库内 .venv（uv 管理的 Python 无法安装 PySide6 时按 README 创建）。
if exist "%TOOL_DIR%..\.venv\Scripts\python.exe" set "PYTHON=%TOOL_DIR%..\.venv\Scripts\python.exe"
start "Serial Workbench" "%PYTHON%" "%TOOL_DIR%..\scripts\serial_gui_qt.py"
