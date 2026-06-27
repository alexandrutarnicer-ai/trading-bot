@echo off
title Trading Bot -- Sesiuni Live
echo ==================================================
echo  Trading Bot -- pornire automata
echo  Astept 90 secunde pentru conectare MT5...
echo ==================================================

rem Incarca variabilele Telegram din registry (User scope)
for /f "delims=" %%i in ('powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable(\"TELEGRAM_TOKEN\",\"User\")"') do set "TELEGRAM_TOKEN=%%i"
for /f "delims=" %%i in ('powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable(\"TELEGRAM_CHAT_ID\",\"User\")"') do set "TELEGRAM_CHAT_ID=%%i"

timeout /t 90 /nobreak
cd /d "c:\trading-bot"
py live\run_all.py
pause
