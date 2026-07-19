@echo off
chcp 65001 >nul 2>&1
setlocal
set "ROOT=%~dp0"
:: %~dp0 include backslash final (ex: C:\trading-bot\). git -C nu accepta calea cu
:: backslash + ghilimele, deci il eliminam.
set "GITROOT=%ROOT:~0,-1%"
set "BRANCH=alex-pc-laptop"
title Trading Bot Update - %BRANCH%

echo.
echo ============================================================
echo   Trading Bot Update - %BRANCH%
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

:: Asigura ca branch-ul local exista si este setat pe remote-ul corect
git -C "%GITROOT%" rev-parse --verify "%BRANCH%" >nul 2>&1
if errorlevel 1 (
    echo  [1/5] Creare branch local pentru %BRANCH% ...
    git -C "%GITROOT%" checkout -B "%BRANCH%" "origin/%BRANCH%" 2>&1
    if errorlevel 1 (
        echo  [!] Nu am putut crea sau comuta la branch-ul %BRANCH%.
        pause
        exit /b 1
    )
) else (
    echo  [1/5] Comutare pe branch-ul %BRANCH% ...
    git -C "%GITROOT%" checkout "%BRANCH%" 2>&1
    if errorlevel 1 (
        echo  [!] Nu am putut comuta la branch-ul %BRANCH%.
        pause
        exit /b 1
    )
)

:: Salveaza hash-ul curent pentru a detecta ce s-a schimbat
for /f %%H in ('git -C "%GITROOT%" rev-parse HEAD 2^>nul') do set "OLD_HASH=%%H"

echo  [2/5] Descarc modificarile din repository ...
git -C "%GITROOT%" fetch origin "%BRANCH%" 2>&1
if errorlevel 1 (
    echo  [!] Eroare la fetch. Verifica conexiunea la internet.
    pause
    exit /b 1
)

:: Verifica daca exista modificari noi
for /f %%H in ('git -C "%GITROOT%" rev-parse "origin/%BRANCH%" 2^>nul') do set "REMOTE_HASH=%%H"

if "%OLD_HASH%"=="%REMOTE_HASH%" (
    echo.
    echo  Botul este deja la zi pe branch-ul %BRANCH%. Nicio modificare disponibila.
    echo.
    pause
    exit /b 0
)

:: [3/5] Pune deoparte modificarile locale (config-ul tau) INAINTE de pull, ca sa
::       nu intre in conflict; le reaplicam dupa update. Daca reaplicarea da
::       conflict, pastram automat versiunea LOCALA (din stash).
echo  [3/5] Salvez modificarile locale ^(git stash^) ...
:: Detectam prin codul de iesire git (nu prin text, ca sa fie independent de limba):
:: `git diff --quiet HEAD` iese cu 1 daca exista modificari locale (tracked), 0 daca e curat.
git -C "%GITROOT%" diff --quiet HEAD
if errorlevel 1 (
    set "STASHED=1"
    git -C "%GITROOT%" stash push -m "update_bot_auto_stash" 2>&1
) else (
    set "STASHED=0"
    echo      Nimic de salvat - arbore de lucru curat.
)

echo  [3/5] Aplic modificarile ^(git pull^) ...
git -C "%GITROOT%" pull origin "%BRANCH%" 2>&1
if errorlevel 1 (
    echo  [!] Eroare la pull.
    if "%STASHED%"=="1" (
        echo      Restaurez modificarile locale ^(git stash pop^) ...
        git -C "%GITROOT%" merge --abort >nul 2>&1
        git -C "%GITROOT%" stash pop 2>&1
    )
    echo      Verifica manual: git status
    pause
    exit /b 1
)

:: Reaplica modificarile locale; la conflict pastreaza versiunea LOCALA (din stash)
if "%STASHED%"=="0" goto after_stash
echo  Reaplic modificarile locale ^(git stash pop^) ...
git -C "%GITROOT%" stash pop 2>&1
git -C "%GITROOT%" diff --name-only --diff-filter=U > "%TEMP%\ub_conf.txt" 2>nul
for %%A in ("%TEMP%\ub_conf.txt") do if %%~zA GTR 0 goto resolve_conflicts
del "%TEMP%\ub_conf.txt" >nul 2>&1
goto after_stash

:resolve_conflicts
echo.
echo  [i] Conflicte la reaplicare - pastrez versiunea LOCALA ^(din stash^):
for /f "usebackq delims=" %%F in ("%TEMP%\ub_conf.txt") do (
    git -C "%GITROOT%" checkout --theirs -- "%%F" >nul 2>&1
    git -C "%GITROOT%" add -- "%%F" >nul 2>&1
    echo      - %%F
)
del "%TEMP%\ub_conf.txt" >nul 2>&1
:: git stash pop NU scoate stash-ul cand da conflict; il scoatem noi acum.
git -C "%GITROOT%" stash drop >nul 2>&1
echo.

:after_stash

:: Detecteaza daca requirements.txt s-a schimbat
git -C "%GITROOT%" diff "%OLD_HASH%" HEAD -- requirements.txt 2>nul | find "+" >nul
if not errorlevel 1 (
    echo  [4/5] requirements.txt modificat - actualizez dependentele Python ...
    py -m pip install -r "%ROOT%requirements.txt" --quiet 2>&1
) else (
    echo  [4/5] requirements.txt neschimbat - skip pip install.
)

:: Detecteaza daca package.json s-a schimbat
git -C "%GITROOT%" diff "%OLD_HASH%" HEAD -- frontend/package.json 2>nul | find "+" >nul
if not errorlevel 1 (
    echo  [5/5] frontend/package.json modificat - actualizez dependentele Node.js ...
    pushd "%ROOT%frontend"
    npm install --silent 2>&1
    popd
) else (
    echo  [5/5] frontend/package.json neschimbat - skip npm install.
)

echo.
echo ============================================================
echo   Update finalizat!
echo ============================================================
echo.
echo  Modificari aplicate:
git -C "%GITROOT%" log --oneline "%OLD_HASH%..HEAD" 2>&1
echo.
if "%STASHED%"=="1" echo  Modificarile tale locale au fost pastrate ^(reaplicate din stash^).
echo.
echo  Porneste dashboard-ul cu start_ui.bat
echo.
pause
endlocal
