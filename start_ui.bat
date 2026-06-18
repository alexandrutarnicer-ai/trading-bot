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
py --version >nul 2>&1
if errorlevel 1 (
    echo  [!] Python nu este instalat sau nu este in PATH.
    echo      Ruleaza setup.bat sau instaleaza Python de la python.org
    pause
    exit /b 1
)

:: Verifica Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo  [!] Node.js nu este instalat sau nu este in PATH.
    echo      Descarca de la: https://nodejs.org (versiunea LTS)
    pause
    exit /b 1
)

echo  [0/3] Opresc instante vechi (daca exista) ...
:: Inchide ferestrele CMD vechi dupa titlu (inchide si procesele din ele)
taskkill /FI "WINDOWTITLE eq TradingBotAPI" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq TradingBotUI" /F >nul 2>&1
:: Fallback: ucide si procesele de pe porturi (in caz ca titlul s-a schimbat)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr LISTENING') do (
    taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5173 " ^| findstr LISTENING') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

echo  [1/3] Pornesc API backend pe portul 8000 ...
start "TradingBotAPI" cmd /k "title TradingBotAPI && cd /d %ROOT% && py -m uvicorn api.main:app --port 8000"

echo  [2/3] Pornesc frontend pe portul 5173 ...
start "TradingBotUI" cmd /k "title TradingBotUI && cd /d %ROOT%frontend && npm run dev"

echo  [3/3] Astept sa porneasca serverele (7 secunde) ...
timeout /t 7 /nobreak >nul

echo  Deschid browser ...
start http://localhost:5173

echo.
echo ============================================================
echo   Dashboard:  http://localhost:5173
echo   API:        http://localhost:8000
echo ============================================================
echo.
echo  Lasa ferestrele TradingBotAPI si TradingBotUI deschise.
echo  Pentru a reporni: dublu-click din nou pe start_ui.bat
echo.
pause >nul
endlocal
