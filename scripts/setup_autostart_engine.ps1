<#
.SYNOPSIS
    Autostart GENERIC pentru un engine (Engine Lifecycle comun). Momentan: daily.
    Creeaza task-ul TradingBot-<Nume> (neelevat, la login + intarziere) si, daca lipseste,
    task-ul PARTAJAT TradingBot-MT5 (acelasi ca la bot / AI Engine).

.PARAMETER Engine
    Cheia engine-ului din tabelul $ENGINES de mai jos (ex: daily).

.NOTES
    Rulat de API (/engines/<id>/autostart/enable) cu UAC, sau manual ca Administrator:
      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
      & "c:\trading-bot\scripts\setup_autostart_engine.ps1" -Engine daily
    Custom Engine (bot) si AI Engine isi pastreaza scripturile dedicate (setup_autostart.ps1 /
    setup_autostart_ai.ps1) - au pasi specifici (profil, Ollama, watchdog) testati in productie;
    API-ul de lifecycle le apeleaza la fel ca pe acesta.
    Task-urile ruleaza NEELEVAT (-RunLevel Limited) ca UI-ul sa poata opri procesele.
    Scriptul e pur ASCII (Windows PowerShell 5.1 il citeste CP1252).
#>
param([Parameter(Mandatory = $true)][string]$Engine)

$ENGINES = @{
    "daily" = @{ Task = "TradingBot-DailyEngine"; Module = "daily_engine"; Label = "Daily Engine";
                 Delay = 150; Bat = "daily_engine\start_daily_engine_auto.bat";
                 Log = "data\daily_engine\autostart.log"; NeedsMt5 = $true }
}

if (-not $ENGINES.ContainsKey($Engine)) {
    Write-Host "[EROARE] Engine necunoscut: $Engine (cunoscute: $($ENGINES.Keys -join ', '))" -ForegroundColor Red
    Read-Host "Apasa Enter pentru iesire"
    exit 1
}
$E       = $ENGINES[$Engine]
$BotDir  = Split-Path $PSScriptRoot -Parent
$BatPath = Join-Path $BotDir $E.Bat
$LogPath = Join-Path $BotDir $E.Log

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  $($E.Label) - Setup Autostart" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Bot dir : $BotDir"

# Python - py.exe (Python Launcher) merge si in sesiuni elevate; venv-ul proiectului are prioritate
$VenvPy = Join-Path $BotDir ".venv\Scripts\python.exe"
if (Test-Path $VenvPy) {
    $PythonExe = $VenvPy
} else {
    $PyLauncher = (Get-Command py -ErrorAction SilentlyContinue).Source
    if ($PyLauncher) {
        $PythonExe = (& py -c "import sys; print(sys.executable)" 2>$null).Trim()
        if (-not $PythonExe -or -not (Test-Path $PythonExe)) { $PythonExe = $PyLauncher }
    } else {
        $PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
    }
}
if (-not $PythonExe) {
    Write-Host "[EROARE] Python nu a fost gasit." -ForegroundColor Red
    Read-Host "Apasa Enter pentru iesire"
    exit 1
}
Write-Host "  Python  : $PythonExe" -ForegroundColor Green

# --- MT5 partajat: creat doar daca lipseste (bot / AI Engine il pot fi creat deja) ---
if ($E.NeedsMt5 -and -not (Get-ScheduledTask -TaskName "TradingBot-MT5" -ErrorAction SilentlyContinue)) {
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
    if (-not $mt5Exe) {
        $mt5Input = Read-Host "MT5 negasit automat. Calea catre terminal64.exe (Enter pentru a sari)"
        if ($mt5Input -and (Test-Path $mt5Input)) { $mt5Exe = $mt5Input }
    }
    if ($mt5Exe) {
        try {
            $a = New-ScheduledTaskAction -Execute $mt5Exe
            $t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
            $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
            Register-ScheduledTask -TaskName "TradingBot-MT5" -Action $a -Trigger $t -Settings $s -RunLevel Highest -Force | Out-Null
            Write-Host "[OK] Task TradingBot-MT5 - MT5 porneste la login (partajat)" -ForegroundColor Green
        } catch {
            Write-Host "[EROARE] Task MT5: $_" -ForegroundColor Red
        }
    } else {
        Write-Host "[ATENTIE] MT5 omis - porneste-l manual (engine-ul reincearca conectarea singur)" -ForegroundColor Yellow
    }
} elseif ($E.NeedsMt5) {
    Write-Host "  MT5     : task TradingBot-MT5 exista deja (partajat)" -ForegroundColor Green
}

# --- .bat minimal: asteapta, porneste engine-ul DETASAT, iese (fara pause/timeout) ---
$delayPing = [int]$E.Delay + 1
$batLines = @(
    '@echo off',
    'chcp 65001 >nul',
    "title $($E.Label) -- Autostart",
    "set `"ELOG=$LogPath`"",
    'echo [%date% %time%] ===== autostart pornit ===== >> "%ELOG%"',
    "echo [%date% %time%] astept $($E.Delay)s (MT5 + retea) >> `"%ELOG%`"",
    "ping -n $delayPing 127.0.0.1 >nul",
    "cd /d `"$BotDir`"",
    'echo [%date% %time%] pornesc engine-ul >> "%ELOG%"',
    "start `"$($E.Label)`" /MIN cmd /c `"`"$PythonExe`" -m $($E.Module) >> `"%ELOG%`" 2>&1`"",
    'echo [%date% %time%] autostart incheiat (lansat detasat) >> "%ELOG%"',
    'exit /b 0'
)
New-Item -ItemType Directory -Force -Path (Split-Path $LogPath -Parent) | Out-Null
[System.IO.File]::WriteAllText($BatPath, ($batLines -join "`r`n") + "`r`n", [System.Text.Encoding]::ASCII)
Write-Host "[OK] Creat: $($E.Bat)" -ForegroundColor Green

try {
    $a = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$BatPath`""
    $t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
         -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
    Register-ScheduledTask -TaskName $E.Task -Action $a -Trigger $t -Settings $s -RunLevel Limited -Force | Out-Null
    Write-Host "[OK] Task $($E.Task) - porneste la login + $($E.Delay)s (neelevat)" -ForegroundColor Green
} catch {
    Write-Host "[EROARE] Task $($E.Task): $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "  Log: $($E.Log)"
Write-Host "  Dezactivare: scripts\remove_autostart_engine.ps1 -Engine $Engine (sau toggle-ul din UI)"
Write-Host ""
Read-Host "Apasa Enter pentru iesire"
