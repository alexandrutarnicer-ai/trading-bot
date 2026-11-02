@echo off
title No Trading - Stop
echo.
echo  Opresc dashboard-ul (API port 8000 + interfata port 5173)...
taskkill /FI "WINDOWTITLE eq TradingBotAPI" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq TradingBotUI"  /F /T >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\kill_ports.ps1" -Ports 8000,5173 >nul 2>&1
echo  [OK] Dashboard oprit.
echo.
echo  ATENTIE: engine-urile (Custom / AI / Daily / Noisy) sunt procese separate si NU se opresc aici.
echo  Opreste-le din Dashboard (butonul Stop al fiecaruia) INAINTE de stop_ui.bat, daca vrei sa le opresti.
echo.
pause
