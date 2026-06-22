@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
set "ROOT=%~dp0"
title Trading Bot — Setup initial

echo.
echo ============================================================
echo   Trading Bot — Setup initial
echo ============================================================
echo.
echo  Instaleaza toate dependentele necesare pentru a rula botul.
echo  Este nevoie de conexiune la internet.
echo.

set "INSTALLED_SOMETHING=0"

:: -- Verifica winget (disponibil implicit pe Windows 11) -------------------
winget --version >nul 2>&1
if errorlevel 1 (
    echo  [!] winget nu este disponibil. Actualizeaza Windows sau instaleaza
    echo      "App Installer" din Microsoft Store si reporneste setup-ul.
    pause
    exit /b 1
)


:: -- 1. Python -------------------------------------------------------------
:: Folosim "py" (Python Launcher) — nu este afectat de Windows Store alias.
echo  [1/5] Verific Python...
py --version >nul 2>&1
if errorlevel 1 (
    echo  [~] Python nu este instalat. Instalez via winget ...
    :: Incercam versiunile recente in ordine — Python.Python.3 (generic) a fost
    :: eliminat din repo; folosim ID-uri explicite cu fallback.
    winget install --id Python.Python.3.13 --exact --silent --accept-package-agreements --accept-source-agreements >nul 2>&1
    if errorlevel 1 (
        winget install --id Python.Python.3.12 --exact --silent --accept-package-agreements --accept-source-agreements >nul 2>&1
        if errorlevel 1 (
            echo  [!] Instalare Python esuata automat.
            echo      Descarca manual de la https://python.org si ruleaza setup.bat din nou.
            pause
            exit /b 1
        )
    )
    set "INSTALLED_SOMETHING=1"
    echo  [+] Python instalat.
) else (
    for /f "tokens=*" %%V in ('py --version 2^>^&1') do echo  [+] %%V deja instalat.
)


:: -- 2. Node.js ------------------------------------------------------------
echo  [2/5] Verific Node.js...
node --version >nul 2>&1
if errorlevel 1 (
    echo  [~] Node.js nu este instalat. Instalez via winget ...
    winget install --id OpenJS.NodeJS.LTS --exact --silent --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo  [!] Instalare Node.js esuata.
        echo      Descarca manual: https://nodejs.org
        pause
        exit /b 1
    )
    set "INSTALLED_SOMETHING=1"
    echo  [+] Node.js instalat.
) else (
    for /f "tokens=*" %%V in ('node --version 2^>^&1') do echo  [+] Node.js %%V deja instalat.
)


:: -- 3. Git ----------------------------------------------------------------
echo  [3/5] Verific Git...
git --version >nul 2>&1
if errorlevel 1 (
    echo  [~] Git nu este instalat. Instalez via winget ...
    winget install --id Git.Git --exact --silent --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo  [!] Instalare Git esuata.
        echo      Descarca manual: https://git-scm.com
        pause
        exit /b 1
    )
    set "INSTALLED_SOMETHING=1"
    echo  [+] Git instalat.
) else (
    for /f "tokens=*" %%V in ('git --version 2^>^&1') do echo  [+] %%V deja instalat.
)


:: -- Daca s-a instalat ceva nou, CMD nu actualizeaza PATH in sesiunea curenta.
:: Deschidem automat o fereastra noua cu PATH proaspat care va continua instalarea.
if "%INSTALLED_SOMETHING%"=="1" (
    echo.
    echo ============================================================
    echo   Finalizeaza instalarea in fereastra noua...
    echo ============================================================
    echo.
    echo  Python / Node.js / Git au fost instalate.
    echo  Deschid automat o fereastra noua pentru a instala
    echo  dependentele Python si frontend...
    echo.
    timeout /t 3 /nobreak >nul
    start "Trading Bot — Finalizare Setup" cmd /k ""%~f0""
    exit /b 0
)


:: -- 4. Dependente Python --------------------------------------------------
echo  [4/5] Instalez dependente Python ...
py -m pip install --upgrade pip --quiet
py -m pip install -r "%ROOT%requirements.txt"
if errorlevel 1 (
    echo  [!] Eroare la pip install. Verifica requirements.txt si conexiunea.
    pause
    exit /b 1
)
echo  [+] Dependente Python OK.
echo.


:: -- 5. Dependente frontend ------------------------------------------------
echo  [5/5] Instalez dependente frontend (npm install) ...
pushd "%ROOT%frontend"
npm install
if errorlevel 1 (
    echo  [!] Eroare la npm install.
    popd
    pause
    exit /b 1
)
popd
echo  [+] Dependente frontend OK.


echo.
echo ============================================================
echo   Setup finalizat cu succes!
echo ============================================================
echo.
echo  Pasi urmatori:
echo.
echo   1. Instaleaza MetaTrader 5 si conecteaza-te la un cont DEMO
echo      (ICMarkets, Pepperstone sau alt broker compatibil)
echo.
echo   2. Dublu-click pe start_ui.bat pentru a porni dashboard-ul
echo.
echo   3. Din dashboard configureaza Telegram (optional)
echo      si porneste botul cu butonul Start
echo.
echo   4. Pentru update-uri viitoare: dublu-click pe update_bot.bat
echo.
pause
endlocal
