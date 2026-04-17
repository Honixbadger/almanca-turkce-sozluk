@echo off
cd /d "%~dp0"
title Almanca-Turkce Sozluk

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "scripts\run_desktop_webview.py"
    exit /b 0
)

python "scripts\run_desktop_webview.py"
