@echo off
cd /d "%~dp0"
title Almanca-Turkce Sozluk (Masaustu)

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "scripts\run_desktop_app.py"
    exit /b 0
)

pyw -3 "scripts\run_desktop_app.py"
