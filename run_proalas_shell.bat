@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM 双进程：Alas WebUI + DAP 外壳（主入口 http://127.0.0.1:8080）
REM DAP 需 Python >=3.8；可用 set DAP_PYTHON=e:\py310\python.exe

if defined DAP_PYTHON (
  "%DAP_PYTHON%" "%~dp0run_proalas_shell.py"
) else if exist "e:\py310\python.exe" (
  "e:\py310\python.exe" "%~dp0run_proalas_shell.py"
) else (
  py -3.10 "%~dp0run_proalas_shell.py" 2>nul || python "%~dp0run_proalas_shell.py"
)

pause
