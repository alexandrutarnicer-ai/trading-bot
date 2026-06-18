@echo off
chcp 65001 >nul 2>&1
setlocal
set "ROOT=%~dp0"
title Trading Bot — Pornire

echo.
echo ============================================================
echo   Trading Bot — Pornire Dashboard
echo ============================================================
echo.

:: Verifica Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [!] Python nu este instalat sau nu este in PATH.
    echo      Ruleaza setup.py sau instaleaza Python de la python.org
    pause
    exit /b 1
)

:: Verifica Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo  [!] Node.js nu este instalat sau nu este in PATH.
    echo      Descarca de la: https://nodejs.org ^(versiunea LTS^)
    pause
    exit /b 1
)

echo  [1/3] Pornesc API backend pe portul 8000 ...
start "Trading Bot — API" cmd /k "cd /d "%ROOT%" && python -m uvicorn api.main:app --port 8000"

echo  [2/3] Pornesc frontend pe portul 5173 ...
start "Trading Bot — UI" cmd /k "cd /d "%ROOT%frontend" && npm run dev"

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
echo  Lasa ferestrele "Trading Bot — API" si "Trading Bot — UI"
echo  deschise cat timp folosesti dashboard-ul.
echo.
echo  Pentru a opri tot: inchide cele doua ferestre de terminal.
echo.
pause >nul
endlocal
