@echo off
cd /d "%~dp0.."
python scripts\enrich_quality.py > logs\enrich_run3.log 2>&1
