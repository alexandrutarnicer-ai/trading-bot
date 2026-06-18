<#
.SYNOPSIS
    Configureaza pornirea automata a Trading Bot la startup Windows.
    Creeaza doua task-uri in Task Scheduler: MT5 si run_all.py (cu 45s delay).

.NOTES
    IMPORTANT: Trebuie rulat ca Administrator.
    Mod recomandat de rulare:
      Win → cauta "PowerShell" → click dreapta → "Run as administrator"
      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
      & "c:\trading-bot\scripts\setup_autostart.ps1"

    Nu trebuie rulat din nou dupa reinstalare Windows — task-urile persista.
    Pentru stergere task-uri: Unregister-ScheduledTask -TaskName "TradingBot-*" -Confirm:$false
#>

$BotDir  = Split-Path $PSScriptRoot -Parent
$BatPath = Join-Path $BotDir "live\start_bot.bat"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Trading Bot — Setup Autostart" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Bot dir : $BotDir"

# Gaseste Python — py.exe (Python Launcher) e in C:\Windows si merge si in sesiuni elevate
# 'python' poate lipsi in sesiuni elevate (Windows Store alias nu e disponibil ca Admin)
$PyLauncher = (Get-Command py -ErrorAction SilentlyContinue).Source
if ($PyLauncher) {
    # Obtine calea executabilului real (ex: C:\Python313\python.exe)
    $PythonExe = (& py -c "import sys; print(sys.executable)" 2>$null).Trim()
    if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
        $PythonExe = $PyLauncher   # fallback: folosim py.exe direct
    }
} else {
    $PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $PythonExe) {
    Write-Host "[EROARE] Python nu a fost gasit." -ForegroundColor Red
    Write-Host "Ruleaza setup.bat pentru a instala Python." -ForegroundColor Red
    Read-Host "`nApasa Enter pentru iesire"
    exit 1
}
Write-Host "  Python  : $PythonExe" -ForegroundColor Green

# Gaseste MT5
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
        Write-Host "  MT5     : omis — porneste-l manual inainte de bot" -ForegroundColor Yellow
        $mt5Exe = $null
    }
}

Write-Host ""

# --- Creeaza live\start_bot.bat ---
# Evitam here-string (@"..."@) — poate avea probleme de encoding pe unele sisteme
$batLines = @(
    '@echo off',
    'title Trading Bot -- Sesiuni Live',
    'echo ==================================================',
    'echo  Trading Bot -- pornire automata',
    'echo  Astept 45 secunde pentru conectare MT5...',
    'echo ==================================================',
    'timeout /t 45 /nobreak',
    "cd /d `"$BotDir`"",
    "`"$PythonExe`" live\run_all.py",
    'pause'
)
[System.IO.File]::WriteAllText($BatPath, ($batLines -join "`r`n"), [System.Text.Encoding]::UTF8)
Write-Host "[OK] Creat: live\start_bot.bat" -ForegroundColor Green

# --- Task Scheduler ---

# Task 1: MT5 la login
if ($mt5Exe) {
    try {
        $a = New-ScheduledTaskAction -Execute $mt5Exe
        $t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
             -DontStopIfGoingOnBatteries -StartWhenAvailable
        Register-ScheduledTask -TaskName "TradingBot-MT5" `
            -Action $a -Trigger $t -Settings $s -RunLevel Highest -Force | Out-Null
        Write-Host "[OK] Task 'TradingBot-MT5'    — MT5 porneste la login" -ForegroundColor Green
    } catch {
        Write-Host "[EROARE] Task MT5: $_" -ForegroundColor Red
    }
}

# Task 2: run_all.py la login (via start_bot.bat, cu 45s delay intern)
try {
    $a2 = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$BatPath`""
    $t2 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $s2 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
          -DontStopIfGoingOnBatteries -StartWhenAvailable `
          -ExecutionTimeLimit (New-TimeSpan -Days 2)
    Register-ScheduledTask -TaskName "TradingBot-RunAll" `
        -Action $a2 -Trigger $t2 -Settings $s2 -RunLevel Highest -Force | Out-Null
    Write-Host "[OK] Task 'TradingBot-RunAll' — run_all.py porneste la login + 45s" -ForegroundColor Green
} catch {
    Write-Host "[EROARE] Task RunAll: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  GATA — ce se intampla la urmatoarea pornire:" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
if ($mt5Exe) {
    Write-Host "  1. MT5 porneste automat la login"
}
Write-Host "  2. Dupa 45 secunde: run_all.py porneste toate sesiunile"
Write-Host "  3. O fereastra CMD ramane deschisa cu statusul botului"
Write-Host ""
Write-Host "  Verificare: cauta 'Task Scheduler' in Start → Task Scheduler Library"
Write-Host "  Stergere:   Unregister-ScheduledTask -TaskName 'TradingBot-*' -Confirm:`$false"
Write-Host ""
Read-Host "Apasa Enter pentru iesire"
