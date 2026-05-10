@echo off
setlocal
cd /d "%~dp0"
python run_solver_benchmarks.py %*
if errorlevel 1 pause
