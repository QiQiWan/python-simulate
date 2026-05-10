@echo off
setlocal
cd /d "%~dp0\..\.."
python tools\run_solver_benchmarks.py %*
pause
