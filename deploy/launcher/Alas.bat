@rem
@echo off

set "_root=%~dp0"
set "_root=%_root:~0,-1%"
cd "%_root%"
echo "%_root%

color F0

set "_pyBin=%_root%\toolkit"
set "_GitBin=%_root%\toolkit\Git\mingw64\bin"
set "_adbBin=%_root%\toolkit\Lib\site-packages\adbutils\binaries"
set "PATH=%_root%\toolkit\alias;%_root%\toolkit\command;%_pyBin%;%_pyBin%\Scripts;%_GitBin%;%_adbBin%;%PATH%"

if not defined DAP_PYTHON if exist "e:\py310\python.exe" set "DAP_PYTHON=e:\py310\python.exe"
set "PROALAS_USE_DAP=1"

title Alas Updater
REM 先修复被 git 覆盖的 gui.py，再决定是否更新
"%_pyBin%\python.exe" "%_root%\deploy\ensure_dap_gui.py"

python -m deploy.installer
if %errorlevel% neq 0 (
    pause >nul
) else (
    REM 更新可能再次覆盖 gui.py
    "%_pyBin%\python.exe" "%_root%\deploy\ensure_dap_gui.py"
    start "Alas" "%_root%\toolkit\webapp\alas.exe"
)