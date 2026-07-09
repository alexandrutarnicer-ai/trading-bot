@echo off
chcp 65001 >nul
title AIEngine
cd /d "%~dp0"

echo ============================================
echo   AI Engine - motor de trading autonom AI
echo ============================================
echo.

rem Porneste serverul Ollama daca nu ruleaza deja (idempotent)
tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find /I "ollama.exe" >nul
if errorlevel 1 (
    echo Pornesc Ollama...
    start "" /B "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
    timeout /t 4 /nobreak >nul
)

echo Pornesc motorul AI (Ctrl+C pentru oprire)...
echo Log: data\ai\engine.log
echo Raport: python -m ai_engine.report
echo.
py -m ai_engine
pause
