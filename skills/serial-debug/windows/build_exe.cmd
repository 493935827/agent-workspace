@echo off
rem 把 Qt 串口工作台打包成单文件 exe（dist\SerialWorkbench.exe）。
rem 需要 .venv 里有 PyInstaller（uv pip install pyinstaller）。
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\pyinstaller.exe" (
  echo 未找到 PyInstaller，请先执行: uv pip install pyinstaller
  pause
  exit /b 1
)
".venv\Scripts\pyinstaller.exe" --noconfirm --clean --onefile --windowed ^
  --name SerialWorkbench ^
  --add-data "scripts\qt-preview-tokens.json;." ^
  scripts\serial_gui_qt.py
if errorlevel 1 (
  echo.
  echo 打包失败，请查看上面的错误信息。
  pause
  exit /b 1
)
echo.
echo 打包完成: %CD%\dist\SerialWorkbench.exe
pause
