@echo off
setlocal enabledelayedexpansion
set "ROOT=%~dp0"
title No Trading - Setup
cd /d "%ROOT%"

echo.
echo ============================================================
echo   No Trading - SETUP (prima instalare / reparare)
echo ============================================================
echo.
echo  Un singur script pentru tot: Python, Node.js, Git, dependente,
echo  directoare, configurari implicite, verificare MT5 si (optional)
echo  AI Engine. Se poate rula oricand din nou - nu sterge nimic.
echo  Este nevoie de internet.
echo.
echo  Optiuni:  setup.bat --with-ai   (instaleaza si Ollama + modelul AI)
echo            setup.bat --no-ai     (fara AI Engine, fara intrebare)
echo            setup.bat --check     (doar verifica, nu instaleaza)
echo.

set "INSTALLED_SOMETHING=0"

:: -- winget (implicit pe Windows 11) -----------------------------------------
set "WINGET_OK=0"
winget --version >nul 2>&1
if not errorlevel 1 set "WINGET_OK=1"
if "%WINGET_OK%"=="0" if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\winget.exe" (
    set "PATH=%LOCALAPPDATA%\Microsoft\WindowsApps;%PATH%"
    winget --version >nul 2>&1
    if not errorlevel 1 set "WINGET_OK=1"
)
if "%WINGET_OK%"=="0" (
    echo  [~] winget lipseste - il instalez...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\install_winget.ps1"
    winget --version >nul 2>&1
    if errorlevel 1 (
        echo.
        echo  [i] winget a fost instalat dar e activ abia intr-o fereastra noua.
        echo      Inchide aceasta fereastra si ruleaza setup.bat din nou.
        echo      Daca nu merge: instaleaza "App Installer" din Microsoft Store.
        pause
        exit /b 1
    )
)

:: -- 1. Python >= 3.10 (prin "py" - Python Launcher, imun la aliasul Windows Store) --
echo  [1/3] Python...
set "PY_OK=0"
py -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "PY_OK=1"
if "%PY_OK%"=="0" (
    echo  [~] Python 3.10+ lipseste - instalez Python 3.12...
    winget install --id Python.Python.3.12 --exact --silent --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo  [!] Instalarea Python a esuat. Instaleaza manual de pe https://python.org
        echo      ^(bifeaza "Add python.exe to PATH"^), apoi ruleaza setup.bat din nou.
        pause
        exit /b 1
    )
    set "INSTALLED_SOMETHING=1"
) else (
    for /f "tokens=*" %%V in ('py --version 2^>^&1') do echo  [OK] %%V
)

:: -- 2. Node.js (Vite cere ^20.19 sau ^>=22.12) -------------------------------
echo  [2/3] Node.js...
set "NODE_OK=0"
for /f "tokens=1,2 delims=v." %%A in ('node --version 2^>nul') do (
    if %%A GEQ 23 set "NODE_OK=1"
    if %%A EQU 22 if %%B GEQ 12 set "NODE_OK=1"
    if %%A EQU 20 if %%B GEQ 19 set "NODE_OK=1"
)
if "%NODE_OK%"=="0" (
    echo  [~] Node.js lipseste sau e prea vechi ^(necesar 20.19 / 22.12+^) - instalez LTS...
    winget install --id OpenJS.NodeJS.LTS --exact --silent --accept-package-agreements --accept-source-agreements
    if errorlevel 1 winget upgrade --id OpenJS.NodeJS.LTS --exact --silent --accept-package-agreements --accept-source-agreements
    set "INSTALLED_SOMETHING=1"
) else (
    for /f "tokens=*" %%V in ('node --version 2^>^&1') do echo  [OK] Node.js %%V
)

:: -- 3. Git (necesar pentru update-uri) -------------------------------------
echo  [3/3] Git...
git --version >nul 2>&1
if errorlevel 1 (
    echo  [~] Git lipseste - instalez...
    winget install --id Git.Git --exact --silent --accept-package-agreements --accept-source-agreements
    set "INSTALLED_SOMETHING=1"
) else (
    for /f "tokens=*" %%V in ('git --version 2^>^&1') do echo  [OK] %%V
)

:: -- PATH nou nu e vizibil in fereastra curenta: continuam intr-una noua ----
if "%INSTALLED_SOMETHING%"=="1" (
    echo.
    echo  Programe noi instalate - continui intr-o fereastra noua ^(PATH proaspat^)...
    ping -n 4 127.0.0.1 >nul
    start "No Trading - Setup (continuare)" cmd /k ""%~f0" %*"
    exit /b 0
)

:: -- Restul (dependente, directoare, configurari, MT5, AI, verificare) -------
echo.
py "%ROOT%scripts\setup_app.py" %*
set "RC=%errorlevel%"
echo.
if "%RC%"=="0" (
    echo  Totul e gata. Porneste aplicatia cu: start_ui.bat
) else (
    echo  Setup-ul nu e complet - vezi lista de mai sus, repara si ruleaza setup.bat din nou.
)
echo.
pause
endlocal & exit /b %RC%
