<#
.SYNOPSIS
    Configureaza pornirea automata a AI Engine la startup Windows.
    Creeaza doua task-uri in Task Scheduler: TradingBot-MT5 (partajat cu botul)
    si TradingBot-AIEngine (Ollama + motor + watchdog, cu asteptare MT5).

.NOTES
    IMPORTANT: Trebuie rulat ca Administrator.
    Mod recomandat de rulare:
      Win -> cauta "PowerShell" -> click dreapta -> "Run as administrator"
      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
      & "c:\trading-bot\scripts\setup_autostart_ai.ps1"

    ALINIERE cu setup_autostart.ps1 (botul pe reguli):
      - Ambele creeaza acelasi task TradingBot-MT5 (idempotent, -Force) - deci
        activarea oricarui autostart (bot SAU AI) porneste MT5. Stergerea unuia
        NU sterge MT5 daca celalalt inca il foloseste (vezi remove_autostart_ai.ps1).
      - AI Engine asteapta 120s (dupa botul cu 90s) ca MT5 sa fie conectat, apoi
        porneste motorul. Motorul iese daca MT5/Ollama nu sunt gata la pornire -
        watchdog-ul (max 5 reincercari/5 min) acopera cazul de conectare lenta.
#>

$BotDir  = Split-Path $PSScriptRoot -Parent
$BatPath = Join-Path $BotDir "ai_engine\start_ai_engine_auto.bat"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  AI Engine - Setup Autostart" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Bot dir : $BotDir"

# Gaseste Python - py.exe (Python Launcher) e in C:\Windows si merge si in sesiuni elevate
$PyLauncher = (Get-Command py -ErrorAction SilentlyContinue).Source
if ($PyLauncher) {
    $PythonExe = (& py -c "import sys; print(sys.executable)" 2>$null).Trim()
    if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
        $PythonExe = $PyLauncher
    }
} else {
    $PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $PythonExe) {
    Write-Host "[EROARE] Python nu a fost gasit." -ForegroundColor Red
    Write-Host "Ruleaza setup_ai_engine.bat pentru a instala Python." -ForegroundColor Red
    Read-Host "Apasa Enter pentru iesire"
    exit 1
}
Write-Host "  Python  : $PythonExe" -ForegroundColor Green

# Gaseste Ollama (serverul LLM local - safety-net-ul consiliului AI)
$ollamaCandidates = @(
    "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
    "$env:PROGRAMFILES\Ollama\ollama.exe",
    "${env:PROGRAMFILES(X86)}\Ollama\ollama.exe"
)
$ollamaExe = $ollamaCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $ollamaExe) {
    $ollamaCmd = (Get-Command ollama -ErrorAction SilentlyContinue).Source
    if ($ollamaCmd) { $ollamaExe = $ollamaCmd }
}
if ($ollamaExe) {
    Write-Host "  Ollama  : $ollamaExe" -ForegroundColor Green
} else {
    Write-Host "  Ollama  : NEGASIT - ruleaza setup_ai_engine.bat mai intai." -ForegroundColor Yellow
    Write-Host "            Motorul AI are nevoie de Ollama ca sursa default." -ForegroundColor Yellow
    $ollamaInput = Read-Host "Introdu calea catre ollama.exe (Enter pentru a folosi 'ollama' din PATH)"
    if ($ollamaInput -and (Test-Path $ollamaInput)) {
        $ollamaExe = $ollamaInput
    } else {
        $ollamaExe = "ollama"   # fallback pe PATH
    }
}

# Gaseste MT5 (partajat cu botul - motorul are nevoie de terminal deschis + DEMO logat)
$mt5Candidates = @(
    "$env:PROGRAMFILES\MetaTrader 5 IC Markets EU\terminal64.exe",
    "$env:PROGRAMFILES\MetaTrader 5 IC Markets\terminal64.exe",
    "$env:PROGRAMFILES\MetaTrader 5\terminal64.exe",
    "${env:PROGRAMFILES(X86)}\MetaTrader 5\terminal64.exe",
    "$env:LOCALAPPDATA\Programs\MetaTrader 5\terminal64.exe",
    "$env:LOCALAPPDATA\Programs\ICMarkets MetaTrader5\terminal64.exe",
    "$env:LOCALAPPDATA\Programs\IC Markets MetaTrader 5\terminal64.exe",
    "$env:LOCALAPPDATA\Programs\ICMarketsEU MetaTrader5\terminal64.exe"
)
$mt5Exe = $mt5Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($mt5Exe) {
    Write-Host "  MT5     : $mt5Exe" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[ATENTIE] MT5 nu a fost gasit automat in locatiile standard." -ForegroundColor Yellow
    $mt5Input = Read-Host "Introdu calea completa catre terminal64.exe (Enter pentru a sari)"
    if ($mt5Input -and (Test-Path $mt5Input)) {
        $mt5Exe = $mt5Input
        Write-Host "  MT5     : $mt5Exe" -ForegroundColor Green
    } else {
        Write-Host "  MT5     : omis - porneste-l manual inainte de motor" -ForegroundColor Yellow
        $mt5Exe = $null
    }
}

Write-Host ""

# --- Creeaza ai_engine\start_ai_engine_auto.bat ---
# Linii Telegram folosesc single-quoted PS strings: '' devine ' in output (batch corect)
$tgLine1 = 'for /f "delims=" %%i in (''powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable(\"TELEGRAM_TOKEN\",\"User\")"'') do set "TELEGRAM_TOKEN=%%i"'
$tgLine2 = 'for /f "delims=" %%i in (''powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable(\"TELEGRAM_CHAT_ID\",\"User\")"'') do set "TELEGRAM_CHAT_ID=%%i"'

# Redesign 2026-07-18 (bat-ul vechi a inghetat la boot fara nicio urma — 5h fara
# motor, task blocat "Running"): (1) LOG la fiecare pas in data\ai\autostart.log
# — orice viitor blocaj devine vizibil; (2) asteptarile folosesc ping -n, nu
# timeout (timeout cere handle de consola interactiv si e fragil sub Task
# Scheduler); (3) FARA pause si FARA rulare in foreground — motorul si watchdog-ul
# se lanseaza DETASAT si bat-ul IESE (task-ul se incheie curat; supravegherea e
# treaba watchdog-ului, care NU contracareaza Stop-ul din UI — acela opreste
# intai watchdog-ul); (4) iesirea motorului e capturata in log (crash-urile
# dinainte de logging nu mai sunt invizibile).
$batLines = @(
    '@echo off',
    'chcp 65001 >nul',
    'title AI Engine -- Autostart',
    "set `"AILOG=$BotDir\data\ai\autostart.log`"",
    'echo [%date% %time%] ===== autostart AI pornit ===== >> "%AILOG%"',
    '',
    'rem Incarca variabilele Telegram din registry (User scope)',
    $tgLine1,
    $tgLine2,
    'echo [%date% %time%] telegram env incarcat >> "%AILOG%"',
    '',
    'rem 1) Porneste Ollama daca nu ruleaza deja (idempotent)',
    'tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find /I "ollama.exe" >nul',
    'if errorlevel 1 (',
    '    echo [%date% %time%] pornesc Ollama >> "%AILOG%"',
    "    start `"`" /B `"$ollamaExe`" serve",
    '    ping -n 11 127.0.0.1 >nul',
    ')',
    'echo [%date% %time%] ollama ok >> "%AILOG%"',
    '',
    'rem 2) Asteapta ~120s ca MT5 sa fie deschis si conectat (dupa bot cu ~30s)',
    'echo [%date% %time%] astept 120s pentru MT5 >> "%AILOG%"',
    'ping -n 121 127.0.0.1 >nul',
    '',
    "cd /d `"$BotDir`"",
    '',
    'rem 3) Watchdog DETASAT (supervizor anti-crash; reporneste motorul daca moare,',
    'rem    max 5 restarturi / verificare la 5 min — acopera si MT5 conectat lent)',
    'echo [%date% %time%] pornesc watchdog >> "%AILOG%"',
    "start `"AI Engine Watchdog`" /MIN `"$PythonExe`" -m ai_engine.watchdog",
    '',
    'rem 4) Motorul AI — DETASAT, cu iesirea capturata in log (crash pre-logging vizibil)',
    'echo [%date% %time%] pornesc motorul AI >> "%AILOG%"',
    "start `"AI Engine`" /MIN cmd /c `"`"$PythonExe`" -m ai_engine >> `"%AILOG%`" 2>&1`"",
    'echo [%date% %time%] autostart AI incheiat (motor + watchdog lansate detasat) >> "%AILOG%"',
    'exit /b 0'
)
[System.IO.File]::WriteAllText($BatPath, ($batLines -join "`r`n") + "`r`n", [System.Text.Encoding]::UTF8)
Write-Host "[OK] Creat: ai_engine\start_ai_engine_auto.bat" -ForegroundColor Green

# --- Task Scheduler ---

# Task 1: MT5 la login (PARTAJAT cu botul - idempotent, -Force il (re)scrie fara probleme)
if ($mt5Exe) {
    try {
        $a = New-ScheduledTaskAction -Execute $mt5Exe
        $t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
             -DontStopIfGoingOnBatteries -StartWhenAvailable
        Register-ScheduledTask -TaskName "TradingBot-MT5" `
            -Action $a -Trigger $t -Settings $s -RunLevel Highest -Force | Out-Null
        Write-Host "[OK] Task TradingBot-MT5      - MT5 porneste la login (partajat cu botul)" -ForegroundColor Green
    } catch {
        Write-Host "[EROARE] Task MT5: $_" -ForegroundColor Red
    }
}

# Task 2: AI Engine la login (via start_ai_engine_auto.bat, cu asteptare 120s interna)
# RunLevel Limited (NU Highest) - proces elevat nu poate fi oprit/inlocuit de
# UI-ul neelevat (Access Denied). Vezi nota din setup_autostart.ps1.
try {
    $a2 = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$BatPath`""
    $t2 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $s2 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
          -DontStopIfGoingOnBatteries -StartWhenAvailable `
          -ExecutionTimeLimit (New-TimeSpan -Days 2)
    Register-ScheduledTask -TaskName "TradingBot-AIEngine" `
        -Action $a2 -Trigger $t2 -Settings $s2 -RunLevel Limited -Force | Out-Null
    Write-Host "[OK] Task TradingBot-AIEngine  - motorul AI porneste la login + 120s (neelevat)" -ForegroundColor Green
} catch {
    Write-Host "[EROARE] Task AIEngine: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  GATA - ce se intampla la urmatoarea pornire:" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
if ($mt5Exe) {
    Write-Host "  1. MT5 porneste automat la login"
}
Write-Host "  2. Ollama porneste (daca nu ruleaza deja)"
Write-Host "  3. Dupa 120 secunde: motorul AI + watchdog-ul pornesc"
Write-Host "  4. O fereastra CMD ramane deschisa cu logul motorului AI"
Write-Host ""
Write-Host "  Watchdog-ul reporneste motorul daca moare (max 5x/5min)."
Write-Host "  Log motor:    data\ai\engine.log"
Write-Host "  Log watchdog: data\ai\watchdog.log"
Write-Host ""
Write-Host "  Verificare: Task Scheduler -> Task Scheduler Library -> TradingBot-AIEngine"
Write-Host "  Dezactivare: scripts\remove_autostart_ai.ps1 (ca Administrator)"
Write-Host ""
Read-Host "Apasa Enter pentru iesire"
