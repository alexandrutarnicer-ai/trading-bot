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
if not errorlevel 1 goto :ollama_ok
echo Pornesc Ollama...
rem Locatia Ollama difera intre masini (C:\...\Programs\Ollama sau D:\Ollama\app) -> PATH primul
set "OLLAMA_EXE="
for /f "delims=" %%O in ('where ollama 2^>nul') do if not defined OLLAMA_EXE set "OLLAMA_EXE=%%O"
if not defined OLLAMA_EXE if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not defined OLLAMA_EXE if exist "D:\Ollama\app\ollama.exe" set "OLLAMA_EXE=D:\Ollama\app\ollama.exe"
if not defined OLLAMA_EXE (
    echo [!] Ollama nu a fost gasit - instaleaza-l de pe ollama.com/download
    goto :ollama_ok
)
start "" /B "%OLLAMA_EXE%" serve
timeout /t 4 /nobreak >nul
:ollama_ok

echo Pornesc motorul AI (Ctrl+C pentru oprire)...
echo Log: data\ai\engine.log
echo Raport: python -m ai_engine.report
echo.
py -m ai_engine
pause
