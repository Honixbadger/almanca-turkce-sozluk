@echo off
cd /d "%~dp0"
python scripts\enrich_quality.py > logs\enrich_quality_run3.log 2>&1
echo Enrich tamamlandi >> logs\enrich_quality_run3.log
