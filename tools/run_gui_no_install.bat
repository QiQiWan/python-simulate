@echo off
setlocal
cd /d "%~dp0"
python run_gui_no_install.py %*
if errorlevel 1 pause
