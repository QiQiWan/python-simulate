@echo off
set PYTHONPATH=src

python -m geoai_simkit check-env
python -m geoai_simkit demo --out-dir exports_root
REM python -m geoai_simkit gui
