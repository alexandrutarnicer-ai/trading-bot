@echo off
chcp 65001 >nul 2>&1
setlocal
set "ROOT=%~dp0"
:: %~dp0 include backslash final (ex: C:\trading-bot\).
:: git -C nu accepta calea cu backslash + ghilimele: "C:\path\" devine "C:\path" fetch...
:: Eliminam backslash-ul final pentru a evita eroarea.
set "GITROOT=%ROOT:~0,-1%"
title Trading Bot — Update

echo.
echo ============================================================
echo   Trading Bot — Update
echo ============================================================
echo.

:: Verifica daca botul ruleaza (PID file activ)
set "PID_FILE=%ROOT%data\run_all.pid"
if exist "%PID_FILE%" (
    set /p BOT_PID=<"%PID_FILE%"
    if defined BOT_PID (
        tasklist /FI "PID eq %BOT_PID%" 2>nul | find "%BOT_PID%" >nul
        if not errorlevel 1 (
            echo  [!] Botul ruleaza ^(PID %BOT_PID%^).
            echo.
            echo      Opreste botul din Dashboard ^(butonul Stop^) inainte de update.
            echo      Pozitiile deschise din MT5 nu sunt afectate de oprire.
            echo.
            pause
            exit /b 1
        )
    )
)

:: Verifica Git
git --version >nul 2>&1
if errorlevel 1 (
    echo  [!] Git nu este instalat sau nu este in PATH.
    pause
    exit /b 1
)

:: Salveaza hash-ul curent pentru a detecta ce s-a schimbat
for /f %%H in ('git -C "%GITROOT%" rev-parse HEAD 2^>nul') do set "OLD_HASH=%%H"

echo  [1/4] Descarc modificarile din repository ...
git -C "%GITROOT%" fetch origin main 2>&1
if errorlevel 1 (
    echo  [!] Eroare la fetch. Verifica conexiunea la internet.
    pause
    exit /b 1
)

:: Verifica daca exista modificari noi
for /f %%H in ('git -C "%GITROOT%" rev-parse origin/main 2^>nul') do set "REMOTE_HASH=%%H"

if "%OLD_HASH%"=="%REMOTE_HASH%" (
    echo.
    echo  Botul este deja la zi. Nicio modificare disponibila.
    echo.
    pause
    exit /b 0
)

echo  [2/4] Aplic modificarile (git pull) ...
git -C "%GITROOT%" pull origin main 2>&1
if errorlevel 1 (
    echo  [!] Eroare la pull. Poate exista un conflict local.
    echo      Ruleaza manual: git status
    pause
    exit /b 1
)

:: Detecteaza daca requirements.txt s-a schimbat
git -C "%GITROOT%" diff "%OLD_HASH%" HEAD -- requirements.txt 2>nul | find "+" >nul
if not errorlevel 1 (
    echo  [3/4] requirements.txt modificat — actualizez dependentele Python ...
    py -m pip install -r "%ROOT%requirements.txt" --quiet 2>&1
) else (
    echo  [3/4] requirements.txt neschimbat — skip pip install.
)

:: Detecteaza daca package.json s-a schimbat
git -C "%GITROOT%" diff "%OLD_HASH%" HEAD -- frontend/package.json 2>nul | find "+" >nul
if not errorlevel 1 (
    echo  [4/4] frontend/package.json modificat — actualizez dependentele Node.js ...
    pushd "%ROOT%frontend"
    npm install --silent 2>&1
    popd
) else (
    echo  [4/4] frontend/package.json neschimbat — skip npm install.
)

:: Afiseaza ce commit-uri s-au adaugat
echo.
echo ============================================================
echo   Update finalizat!
echo ============================================================
echo.
echo  Modificari aplicate:
git -C "%GITROOT%" log --oneline "%OLD_HASH%..HEAD" 2>&1
echo.
echo  Porneste dashboard-ul cu start_ui.bat
echo.
pause
endlocal
