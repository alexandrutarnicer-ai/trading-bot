@echo off
chcp 65001 >nul
title Telegram Bridge -- Autostart
set "BRLOG=C:\trading-bot\data\telegram_bridge_autostart.log"
echo [%date% %time%] ===== autostart punte pornit ===== >> "%BRLOG%"

rem Fallback Telegram din registry (User scope) - puntea citeste si data\telegram_config.json
for /f "delims=" %%i in ('powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable(\"TELEGRAM_TOKEN\",\"User\")"') do set "TELEGRAM_TOKEN=%%i"
for /f "delims=" %%i in ('powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable(\"TELEGRAM_CHAT_ID\",\"User\")"') do set "TELEGRAM_CHAT_ID=%%i"

rem Asteapta ~60s (dupa bot/AI) ca reteaua + API-ul local sa fie gata
echo [%date% %time%] astept 60s >> "%BRLOG%"
ping -n 61 127.0.0.1 >nul

cd /d "C:\trading-bot"
echo [%date% %time%] pornesc puntea >> "%BRLOG%"
start "Telegram Bridge" /MIN cmd /c ""C:\Users\alext\AppData\Local\Programs\Python\Python314\python.exe" -m telegram_bridge >> "%BRLOG%" 2>&1"
echo [%date% %time%] autostart punte incheiat (lansata detasat) >> "%BRLOG%"
exit /b 0
