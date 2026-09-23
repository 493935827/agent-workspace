@echo off
setlocal
set "TOOL_DIR=%~dp0"
set "PYTHON=python"
start "Serial GUI" "%PYTHON%" "%TOOL_DIR%..\scripts\serial_gui.py"
