@echo off
chcp 65001 >nul 2>&1
setlocal
set "ROOT=%~dp0"
title TradingBot-Start

echo.
echo ============================================================
echo   Trading Bot - Pornire Dashboard
echo ============================================================
echo.

:: Verifica Python
echo  [CHECK] Verific Python...
py --version
if errorlevel 1 (
    echo  [EROARE] Python nu este gasit!
    pause
    exit /b 1
)
echo  [OK] Python gasit.
echo.

:: Verifica Node.js
echo  [CHECK] Verific Node.js...
node --version
if errorlevel 1 (
    echo  [EROARE] Node.js nu este gasit!
    pause
    exit /b 1
)
echo  [OK] Node.js gasit.
echo.

:: Opreste procese vechi
echo  [0/3] Opresc instante vechi...
taskkill /FI "WINDOWTITLE eq TradingBotAPI" /F /T 2>nul
taskkill /FI "WINDOWTITLE eq TradingBotUI"  /F /T 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\kill_ports.ps1" -Ports 8000,5173 2>nul
timeout /t 2 /nobreak >nul
echo  [0/3] Procese vechi oprite.
echo.

:: Porneste API
echo  [1/3] Pornesc API backend pe portul 8000...
start "TradingBotAPI" cmd /k "title TradingBotAPI && cd /d %ROOT% && py -m uvicorn api.main:app --port 8000"
echo  [1/3] Fereastra TradingBotAPI deschisa.
echo.

:: Porneste Frontend
echo  [2/3] Pornesc frontend pe portul 5173...
start "TradingBotUI" cmd /k "title TradingBotUI && cd /d %ROOT%frontend && npm run dev"
echo  [2/3] Fereastra TradingBotUI deschisa.
echo.

:: Asteapta si verifica
echo  [3/3] Astept 8 secunde sa porneasca serverele...
timeout /t 8 /nobreak >nul

echo  [CHECK] Verific portul 8000 (API)...
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -EA SilentlyContinue) { Write-Host '  [OK] API ruleaza pe portul 8000' } else { Write-Host '  [ATENTIE] API NU ruleaza inca pe portul 8000 - verifica fereastra TradingBotAPI' }"

echo  [CHECK] Verific portul 5173 (Frontend)...
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 5173 -State Listen -EA SilentlyContinue) { Write-Host '  [OK] Frontend ruleaza pe portul 5173' } else { Write-Host '  [ATENTIE] Frontend NU ruleaza inca pe portul 5173 - verifica fereastra TradingBotUI' }"

echo.
echo  Deschid browser...
start http://localhost:5173

echo.
echo ============================================================
echo   Dashboard:  http://localhost:5173
echo   API:        http://localhost:8000
echo ============================================================
echo.
echo  Lasa ferestrele TradingBotAPI si TradingBotUI deschise.
echo  Aceasta fereastra (TradingBot-Start) se poate inchide.
echo.
pause
endlocal