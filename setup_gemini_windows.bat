@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 scripts\configure_gemini.py
) else (
  python scripts\configure_gemini.py
)
pause
