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
      - Bat-ul AI e minimal si iese instant: porneste Ollama + lanseaza
        watchdog-ul. Watchdog-ul PORNESTE motorul si asteapta MT5/Ollama prin
        retry (fereastra de boot ~15 min), apoi il reporneste daca moare.
        Nicio pauza lunga in bat (ping-urile inghetau la boot - fix 2026-08-08).
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

# Redesign 2026-08-08 (bug: bat-ul VECHI inghetat pe pauzele `ping` la boot -
# watchdog-ul era lansat DUPA acele pauze, deci cand bat-ul se bloca, nimic nu
# mai pornea motorul; s-a intamplat de 6+ ori). ACUM bat-ul e minimal si FARA
# pauze lungi: incarca env Telegram -> porneste Ollama (fara asteptare) -> lanseaza
# DOAR watchdog-ul (detasat) -> iese instant. Toata asteptarea MT5/Ollama e MUTATA
# in watchdog (Python, fiabil): el porneste motorul si reincearca pe o fereastra
# de boot pana "prinde", apoi il reporneste daca moare. Un singur loc care
# lanseaza motorul = watchdog-ul (fara dubluri). Vezi ai_engine/watchdog.py.
# Fiecare pas ramane logat in data\ai\autostart.log (blocaj viitor = vizibil).
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
    'rem 1) Porneste Ollama daca nu ruleaza deja (idempotent, FARA asteptare -',
    'rem    watchdog-ul asteapta prin retry ca Ollama+MT5 sa fie gata)',
    'tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find /I "ollama.exe" >nul',
    'if errorlevel 1 (',
    '    echo [%date% %time%] pornesc Ollama >> "%AILOG%"',
    "    start `"`" /B `"$ollamaExe`" serve",
    ')',
    'echo [%date% %time%] ollama lansat (fara asteptare) >> "%AILOG%"',
    '',
    "cd /d `"$BotDir`"",
    '',
    'rem 2) Watchdog DETASAT - el PORNESTE motorul si asteapta MT5/Ollama (retry pe',
    'rem    fereastra de boot), apoi il reporneste daca moare. NICIO pauza lunga in',
    'rem    bat: ping-urile de asteptare inghetau la boot si watchdog-ul nu mai pornea.',
    'echo [%date% %time%] pornesc watchdog >> "%AILOG%"',
    "start `"AI Engine Watchdog`" /MIN `"$PythonExe`" -m ai_engine.watchdog",
    'echo [%date% %time%] autostart AI incheiat (watchdog lansat; el porneste motorul) >> "%AILOG%"',
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

# Task 2: AI Engine la login (via start_ai_engine_auto.bat, minimal + iese instant;
# watchdog-ul porneste motorul si asteapta MT5/Ollama prin retry)
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
    Write-Host "[OK] Task TradingBot-AIEngine  - watchdog-ul porneste motorul AI la login (neelevat)" -ForegroundColor Green
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
Write-Host "  3. Watchdog-ul porneste imediat si PORNESTE motorul AI"
Write-Host "  4. Watchdog-ul asteapta MT5/Ollama prin retry (pana ~15 min) pana motorul prinde"
Write-Host ""
Write-Host "  Watchdog-ul reporneste apoi motorul daca moare (max 5x/5min)."
Write-Host "  Log motor:    data\ai\engine.log"
Write-Host "  Log watchdog: data\ai\watchdog.log"
Write-Host ""
Write-Host "  Verificare: Task Scheduler -> Task Scheduler Library -> TradingBot-AIEngine"
Write-Host "  Dezactivare: scripts\remove_autostart_ai.ps1 (ca Administrator)"
Write-Host ""
Read-Host "Apasa Enter pentru iesire"
