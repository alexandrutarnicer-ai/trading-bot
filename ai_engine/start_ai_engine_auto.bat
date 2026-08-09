@echo off
chcp 65001 >nul
title AI Engine -- Autostart
set "AILOG=C:\trading-bot\data\ai\autostart.log"
echo [%date% %time%] ===== autostart AI pornit ===== >> "%AILOG%"

rem Incarca variabilele Telegram din registry (User scope)
for /f "delims=" %%i in ('powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable(\"TELEGRAM_TOKEN\",\"User\")"') do set "TELEGRAM_TOKEN=%%i"
for /f "delims=" %%i in ('powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable(\"TELEGRAM_CHAT_ID\",\"User\")"') do set "TELEGRAM_CHAT_ID=%%i"
echo [%date% %time%] telegram env incarcat >> "%AILOG%"

rem 1) Porneste Ollama daca nu ruleaza deja (idempotent, FARA asteptare -
rem    watchdog-ul asteapta prin retry ca Ollama+MT5 sa fie gata)
tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find /I "ollama.exe" >nul
if errorlevel 1 (
    echo [%date% %time%] pornesc Ollama >> "%AILOG%"
    start "" /B "C:\Users\alext\AppData\Local\Programs\Ollama\ollama.exe" serve
)
echo [%date% %time%] ollama lansat (fara asteptare) >> "%AILOG%"

cd /d "C:\trading-bot"

rem 2) Watchdog DETASAT - el PORNESTE motorul si asteapta MT5/Ollama (retry pe
rem    fereastra de boot), apoi il reporneste daca moare. NICIO pauza lunga in
rem    bat: ping-urile de asteptare inghetau la boot si watchdog-ul nu mai pornea.
echo [%date% %time%] pornesc watchdog >> "%AILOG%"
start "AI Engine Watchdog" /MIN "C:\Users\alext\AppData\Local\Programs\Python\Python314\python.exe" -m ai_engine.watchdog
echo [%date% %time%] autostart AI incheiat (watchdog lansat; el porneste motorul) >> "%AILOG%"
exit /b 0
