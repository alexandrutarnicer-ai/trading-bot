@echo off
chcp 65001 >nul
title AI Engine -- Autostart
echo ==================================================
echo  AI Engine -- pornire automata
echo ==================================================

rem Incarca variabilele Telegram din registry (User scope)
for /f "delims=" %%i in ('powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable(\"TELEGRAM_TOKEN\",\"User\")"') do set "TELEGRAM_TOKEN=%%i"
for /f "delims=" %%i in ('powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable(\"TELEGRAM_CHAT_ID\",\"User\")"') do set "TELEGRAM_CHAT_ID=%%i"

rem 1) Porneste Ollama daca nu ruleaza deja (idempotent)
tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find /I "ollama.exe" >nul
if errorlevel 1 (
    echo Pornesc Ollama...
    start "" /B "C:\Users\alext\AppData\Local\Programs\Ollama\ollama.exe" serve
    timeout /t 10 /nobreak >nul
)

rem 2) Asteapta ca MT5 sa fie deschis si conectat (dupa bot cu ~30s)
echo  Astept 120 secunde pentru conectare MT5...
timeout /t 120 /nobreak

cd /d "C:\trading-bot"

rem 3) Watchdog (supervizor anti-crash, fereastra minimizata)
start "AI Engine Watchdog" /MIN "C:\Users\alext\AppData\Local\Programs\Python\Python314\python.exe" -m ai_engine.watchdog

rem 4) Motorul AI (foreground, log vizibil in aceasta fereastra)
"C:\Users\alext\AppData\Local\Programs\Python\Python314\python.exe" -m ai_engine
pause
