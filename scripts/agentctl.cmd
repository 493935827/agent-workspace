@echo off
rem Run agentctl from this workspace without a global install.
rem Uses the workspace .venv when present, otherwise system python.
setlocal
set "HERE=%~dp0"
if exist "%HERE%..\.venv\Scripts\python.exe" (
  "%HERE%..\.venv\Scripts\python.exe" -m agentctl %*
) else (
  python -m agentctl %*
)
rem Exiting the batch file also ends setlocal; preserve Python's exit code.
exit /b %ERRORLEVEL%
