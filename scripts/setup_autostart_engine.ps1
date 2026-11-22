<#
.SYNOPSIS
    Autostart GENERIC (Engine Lifecycle comun): daily / ai / app (API + monitorizare).
    Creeaza task-ul TradingBot-<Nume> (neelevat, la login) care ruleaza DIRECT
    "pythonw -m startup_gate --engine <id>" - pornire CONDITIONATA de dependente (internet, MT5 conectat
    + cont, Ollama pentru AI, configuratie), fara .bat si fara "ping" (care inghetau la boot).
    Daca lipseste, creeaza si task-ul PARTAJAT TradingBot-MT5 (acelasi ca la bot).

.PARAMETER Engine
    Cheia din tabelul $ENGINES de mai jos. Noisy NU are autostart (refuzat).

.NOTES
    Rulat de API (/engines/<id>/autostart/enable) cu UAC, sau manual ca Administrator:
      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
      & "c:\trading-bot\scripts\setup_autostart_engine.ps1" -Engine daily
    Custom Engine (bot) isi pastreaza scriptul dedicat (setup_autostart.ps1 - profil, sesiuni).
    Task-urile ruleaza NEELEVAT (-RunLevel Limited) ca UI-ul sa poata opri procesele.
    Scriptul e pur ASCII (Windows PowerShell 5.1 il citeste CP1252).
#>
param([Parameter(Mandatory = $true)][string]$Engine)

$ENGINES = @{
    "daily" = @{ Task = "TradingBot-DailyEngine"; Label = "Daily Engine"; NeedsMt5 = $true;
                 OldBat = "daily_engine\start_daily_engine_auto.bat" }
    "ai"    = @{ Task = "TradingBot-AIEngine"; Label = "AI Engine"; NeedsMt5 = $true;
                 OldBat = "ai_engine\start_ai_engine_auto.bat" }
    "app"   = @{ Task = "TradingBot-API"; Label = "Aplicatia (API + monitorizare)"; NeedsMt5 = $false; OldBat = "" }
    "special" = @{ Task = "TradingBot-SpecialEngine"; Label = "Special Engine"; NeedsMt5 = $true; OldBat = "" }
}

if ($Engine -eq "noisy") {
    Write-Host "[REFUZAT] Noisy Engine NU are autostart (pornire doar manuala, cu confirmare)." -ForegroundColor Yellow
    Read-Host "Apasa Enter pentru iesire"
    exit 1
}
if (-not $ENGINES.ContainsKey($Engine)) {
    Write-Host "[EROARE] Engine necunoscut: $Engine (cunoscute: $($ENGINES.Keys -join ', '))" -ForegroundColor Red
    Read-Host "Apasa Enter pentru iesire"
    exit 1
}
$E      = $ENGINES[$Engine]
$BotDir = Split-Path $PSScriptRoot -Parent

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  $($E.Label) - Setup Autostart (pornire conditionata)" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Bot dir : $BotDir"

# Python - venv-ul proiectului are prioritate; py.exe (Python Launcher) merge si in sesiuni elevate
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
# pythonw.exe (fara fereastra de consola) langa python.exe, daca exista
$PythonW = Join-Path (Split-Path $PythonExe -Parent) "pythonw.exe"
if (-not (Test-Path $PythonW)) { $PythonW = $PythonExe }
Write-Host "  Python  : $PythonW" -ForegroundColor Green

# --- MT5 partajat: creat doar daca lipseste (bot / alt engine il pot fi creat deja) ---
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
        Write-Host "[ATENTIE] MT5 omis - startup_gate il porneste singur prin MetaTrader5.initialize()" -ForegroundColor Yellow
    }
} elseif ($E.NeedsMt5) {
    Write-Host "  MT5     : task TradingBot-MT5 exista deja (partajat)" -ForegroundColor Green
}

# --- vechiul .bat (asteptare cu ping) nu mai e folosit ---
if ($E.OldBat) {
    $old = Join-Path $BotDir $E.OldBat
    if (Test-Path $old) { Remove-Item $old -Force; Write-Host "[OK] Sters vechiul $($E.OldBat)" -ForegroundColor Green }
}

try {
    $a = New-ScheduledTaskAction -Execute $PythonW -Argument "-m startup_gate --engine $Engine" -WorkingDirectory $BotDir
    $t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
         -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $E.Task -Action $a -Trigger $t -Settings $s -RunLevel Limited -Force | Out-Null
    Write-Host "[OK] Task $($E.Task) - la login: verifica dependentele, apoi porneste (neelevat)" -ForegroundColor Green
} catch {
    Write-Host "[EROARE] Task $($E.Task): $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "  Jurnal pornire: data\...\autostart.log (vezi Ghidul - Pornire automata)"
Write-Host "  Intarzieri / asteptare maxima: data\autostart_config.json (optional)"
Write-Host "  Dezactivare: scripts\remove_autostart_engine.ps1 -Engine $Engine (sau toggle-ul din UI)"
Write-Host ""
Read-Host "Apasa Enter pentru iesire"
