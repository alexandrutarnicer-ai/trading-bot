@echo off
chcp 65001 >nul
title AI Engine -- Autostart
set "AILOG=C:\trading-bot\data\ai\autostart.log"
echo [%date% %time%] ===== autostart AI pornit ===== >> "%AILOG%"

rem Incarca variabilele Telegram din registry (User scope)
for /f "delims=" %%i in ('powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable(\"TELEGRAM_TOKEN\",\"User\")"') do set "TELEGRAM_TOKEN=%%i"
for /f "delims=" %%i in ('powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable(\"TELEGRAM_CHAT_ID\",\"User\")"') do set "TELEGRAM_CHAT_ID=%%i"
echo [%date% %time%] telegram env incarcat >> "%AILOG%"

rem 1) Porneste Ollama daca nu ruleaza deja (idempotent)
tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find /I "ollama.exe" >nul
if errorlevel 1 (
    echo [%date% %time%] pornesc Ollama >> "%AILOG%"
    start "" /B "C:\Users\alext\AppData\Local\Programs\Ollama\ollama.exe" serve
    ping -n 11 127.0.0.1 >nul
)
echo [%date% %time%] ollama ok >> "%AILOG%"

rem 2) Asteapta ~120s ca MT5 sa fie deschis si conectat (dupa bot cu ~30s)
echo [%date% %time%] astept 120s pentru MT5 >> "%AILOG%"
ping -n 121 127.0.0.1 >nul

cd /d "C:\trading-bot"

rem 3) Watchdog DETASAT (supervizor anti-crash; reporneste motorul daca moare,
rem    max 5 restarturi / verificare la 5 min — acopera si MT5 conectat lent)
echo [%date% %time%] pornesc watchdog >> "%AILOG%"
start "AI Engine Watchdog" /MIN "C:\Users\alext\AppData\Local\Programs\Python\Python314\python.exe" -m ai_engine.watchdog

rem 4) Motorul AI — DETASAT, cu iesirea capturata in log (crash pre-logging vizibil)
echo [%date% %time%] pornesc motorul AI >> "%AILOG%"
start "AI Engine" /MIN cmd /c ""C:\Users\alext\AppData\Local\Programs\Python\Python314\python.exe" -m ai_engine >> "%AILOG%" 2>&1"
echo [%date% %time%] autostart AI incheiat (motor + watchdog lansate detasat) >> "%AILOG%"
exit /b 0
