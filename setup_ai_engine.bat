@echo off
chcp 65001 >nul
title SetupAIEngine
cd /d "%~dp0"

echo ==================================================
echo   Instalare AI Engine (laptop / PC nou)
echo ==================================================
echo.
echo Pasi: 1) Python + dependinte  2) Ollama  3) Model AI  4) Verificare
echo Necesita: internet + MT5 instalat si logat pe cont DEMO (pentru pasul final)
echo.

rem ── 1. Python ──────────────────────────────────────────────────────────────
where py >nul 2>nul
if errorlevel 1 (
    echo [1/4] Instalez Python via winget...
    winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
    echo     Deschide o fereastra NOUA de terminal si ruleaza scriptul din nou
    echo     ^(PATH-ul nou nu e vizibil in fereastra curenta^).
    pause
    exit /b 1
) else (
    echo [1/4] Python: OK
)

echo     Instalez dependintele pip...
py -m pip install --quiet MetaTrader5 pandas numpy scipy fastapi uvicorn
if errorlevel 1 (
    echo     EROARE la pip install — verifica conexiunea la internet.
    pause
    exit /b 1
)

rem ── 2. Ollama ──────────────────────────────────────────────────────────────
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    echo [2/4] Ollama: OK
) else (
    echo [2/4] Instalez Ollama via winget...
    winget install --id Ollama.Ollama -e --silent --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo     EROARE la instalarea Ollama.
        pause
        exit /b 1
    )
)

rem Porneste serverul daca nu ruleaza
tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find /I "ollama.exe" >nul
if errorlevel 1 (
    start "" /B "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
    timeout /t 5 /nobreak >nul
)

rem ── 3. Modelul AI ──────────────────────────────────────────────────────────
echo [3/4] Descarc modelul qwen3:8b (~5 GB — poate dura 5-20 min)...
echo     NOTA: pe un laptop fara GPU dedicat, foloseste un model mai mic:
echo           editeaza ai_engine\config.json: "model": "qwen3:4b"
echo           si ruleaza: ollama pull qwen3:4b
"%LOCALAPPDATA%\Programs\Ollama\ollama.exe" pull qwen3:8b
if errorlevel 1 (
    echo     EROARE la descarcarea modelului.
    pause
    exit /b 1
)

rem ── 4. Verificare ──────────────────────────────────────────────────────────
echo [4/4] Rulez verificarile AI Engine (include un consiliu AI live)...
py -m ai_engine.selftest
if errorlevel 1 (
    echo.
    echo Verificarile au ESUAT — vezi erorile de mai sus.
    echo Cel mai frecvent: MT5 inchis sau cont non-DEMO ^(testul de consiliu
    echo merge si fara MT5^).
    pause
    exit /b 1
)

echo.
echo ==================================================
echo   Instalare COMPLETA.
echo   Pornire motor:  start_ai_engine.bat
echo   Raport:         py -m ai_engine.report
echo ==================================================
pause
