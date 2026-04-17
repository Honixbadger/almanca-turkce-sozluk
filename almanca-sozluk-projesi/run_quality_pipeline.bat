@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ════════════════════════════════════════════════
echo  Kalite Gelistirme Pipeline
echo ════════════════════════════════════════════════
echo.

echo [1/5] GPT fiil kaliplari import ediliyor...
python scripts/import_from_codex.py output/codex/ --gorev fiil_kaliplari
if errorlevel 1 goto :hata
echo.

echo [2/5] Duplikasyon temizleniyor (336 fazla kayit)...
python scripts/cleanup_duplicates.py
if errorlevel 1 goto :hata
echo.

echo [3/5] Bilesik kelime bolucusu calistiriliyor (19.062 kayit)...
python scripts/enrich_compound_split.py
if errorlevel 1 goto :hata
echo.

echo [4/5] Turkce tanim cevirisi basliyor (8.147 kayit, Groq)...
python scripts/enrich_tanim_turkce.py
if errorlevel 1 goto :hata
echo.

echo [5/5] Kisa/hatali Turkce ceviriler duzeltiliyor (359 kayit)...
python scripts/enrich_groq_translations5.py
if errorlevel 1 goto :hata
echo.

echo ════════════════════════════════════════════════
echo  Pipeline tamamlandi!
echo ════════════════════════════════════════════════
goto :son

:hata
echo.
echo HATA: Pipeline durdu. Yukaridaki hataya bakin.
exit /b 1

:son
