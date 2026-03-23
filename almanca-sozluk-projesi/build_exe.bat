@echo off
chcp 65001 > nul
cd /d "%~dp0"
title Almanca-Turkce Sozluk - EXE Build

echo.
echo  ==========================================
echo   Almanca-Turkce Sozluk - EXE Olusturuluyor
echo  ==========================================
echo.

:: PyInstaller kur (zaten kuruluysa hata vermez)
echo [0/3] PyInstaller kontrol ediliyor...
py -3 -m pip install pyinstaller --quiet

echo [1/3] Eski build temizleniyor...
if exist "build" rmdir /s /q "build"
if exist "dist\AlmancaSozluk" rmdir /s /q "dist\AlmancaSozluk"

echo [2/3] EXE olusturuluyor...
py -3 -c "from PyInstaller.__main__ import run; run()" ^
    --name "AlmancaSozluk" ^
    --icon "assets\branding\dictionary_logo.ico" ^
    --windowed ^
    --onedir ^
    --add-data "output\dictionary.json;output" ^
    --add-data "output\word_image_manifest.json;output" ^
    --add-data "assets\branding\dictionary_logo.png;assets\branding" ^
    --add-data "assets\branding\dictionary_logo.ico;assets\branding" ^
    --add-data "data\manual;data\manual" ^
    --add-data "scripts\run_frontend.py;scripts" ^
    --hidden-import "PIL._tkinter_finder" ^
    --hidden-import "tkinter" ^
    --hidden-import "tkinter.ttk" ^
    --collect-all "Pillow" ^
    --noconfirm ^
    "scripts\run_desktop_app.py"

if errorlevel 1 (
    echo.
    echo [HATA] EXE olusturulamadi!
    pause
    exit /b 1
)

echo [3/3] Tamamlandi!
echo.
echo  EXE konumu: dist\AlmancaSozluk\AlmancaSozluk.exe
echo.
echo  Dagitmak icin "dist\AlmancaSozluk\" klasorunu paylasin.
echo.
pause
