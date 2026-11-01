@echo off
chcp 65001 >nul 2>&1
setlocal
title Update vlad-live
:: Aduce codul nou pe vlad-live FARA sa piarda configurarile locale (profil, Setari Globale,
:: config AI / Daily / Noisy, fus orar): stash -> update -> reaplicare (la conflict ramane
:: versiunea ta). Toata logica e in scripts\update_vlad_live.py (testat: test_update_vlad_live.py).
set "ROOT=%~dp0"
set "PY="
where py >nul 2>&1 && set "PY=py"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo  [!] Python nu este instalat sau nu e in PATH.
    pause
    exit /b 1
)
%PY% "%ROOT%scripts\update_vlad_live.py"
echo.
pause
endlocal
