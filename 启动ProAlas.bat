@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "_root=%~dp0"
set "_root=%_root:~0,-1%"
cd /d "%_root%"

color F0
set "_pyBin=%_root%\toolkit"
set "_GitBin=%_root%\toolkit\Git\mingw64\bin"
set "_adbBin=%_root%\toolkit\Lib\site-packages\adbutils\binaries"
set "PATH=%_root%\toolkit\alias;%_root%\toolkit\command;%_pyBin%;%_pyBin%\Scripts;%_GitBin%;%_adbBin%;%PATH%"

if not defined DAP_PYTHON if exist "e:\py310\python.exe" set "DAP_PYTHON=e:\py310\python.exe"
set "PROALAS_USE_DAP=1"

title ProAlas OSS
echo 请先关闭所有 Alas / Electron 窗口，再继续...
timeout /t 2 /nobreak >nul

echo [1/2] 修复 gui.py + 打补丁 Electron（顶层打开 DAP）...
if exist "e:\py310\python.exe" (
  "e:\py310\python.exe" "%_root%\deploy\ensure_dap_gui.py"
) else (
  "%_pyBin%\python.exe" "%_root%\deploy\ensure_dap_gui.py"
)
if errorlevel 1 (
  echo 失败：请彻底退出 Alas.exe 后重试
  pause
  exit /b 1
)

echo [2/2] 启动 Electron（应直接显示 DAP 登录，可点进入）...
start "Alas" "%_root%\toolkit\webapp\alas.exe"
echo 设备选 alas，密码留空，点「进入」。
