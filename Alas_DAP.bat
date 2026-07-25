@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not defined DAP_PYTHON if exist "e:\py310\python.exe" set "DAP_PYTHON=e:\py310\python.exe"
set "PROALAS_USE_DAP=1"
call "%~dp0启动ProAlas.bat"
