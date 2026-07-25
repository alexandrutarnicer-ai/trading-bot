<#
.SYNOPSIS
    Configureaza pornirea automata a lui EMA (asistentul vocal) la startup Windows.
    Creeaza un singur task: TradingBot-VoiceEMA (daemon standalone, aditiv, read-only).

.NOTES
    IMPORTANT: Trebuie rulat ca Administrator.
      Win -> cauta "PowerShell" -> click dreapta -> "Run as administrator"
      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
      & "c:\trading-bot\scripts\setup_autostart_voice.ps1"

    EMA NU are nevoie de MT5/Ollama/Telegram (proces separat, doar citeste stare +
    API local + microfon). Are nevoie de Python + dependintele audio instalate
    (ruleaza setup_voice_bridge.bat mai intai). Task-ul ruleaza NEELEVAT
    (-RunLevel Limited) ca UI-ul neelevat sa il poata opri.
    Scriptul e pur ASCII (Windows PowerShell 5.1 il citeste CP1252).

    ATENTIE: cu autostart activ, EMA porneste microfonul la fiecare login (mod
    "name" asculta continuu). Pune-o pe pauza cand nu vrei sa asculte (buton UI /
    "EMA culca-te"), sau foloseste wake_mode "ptt" in data\voice_bridge.json.
#>

$BotDir  = Split-Path $PSScriptRoot -Parent
$BatPath = Join-Path $BotDir "voice_bridge\start_voice_auto.bat"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  EMA (asistent vocal) - Setup Autostart" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Bot dir : $BotDir"

# Gaseste Python - py.exe (Python Launcher) merge si in sesiuni elevate
$PyLauncher = (Get-Command py -ErrorAction SilentlyContinue).Source
if ($PyLauncher) {
    $PythonExe = (& py -c "import sys; print(sys.executable)" 2>$null).Trim()
    if (-not $PythonExe -or -not (Test-Path $PythonExe)) { $PythonExe = $PyLauncher }
} else {
    $PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $PythonExe) {
    Write-Host "[EROARE] Python nu a fost gasit." -ForegroundColor Red
    Read-Host "Apasa Enter pentru iesire"
    exit 1
}
Write-Host "  Python  : $PythonExe" -ForegroundColor Green

# Avertisment daca dependintele audio nu par instalate
$check = (& $PythonExe -c "import importlib.util as u; print(1 if u.find_spec('faster_whisper') and u.find_spec('sounddevice') else 0)" 2>$null).Trim()
if ($check -ne "1") {
    Write-Host "  [ATENTIE] Dependintele audio par sa lipseasca - ruleaza" -ForegroundColor Yellow
    Write-Host "            setup_voice_bridge.bat inainte, altfel EMA nu porneste." -ForegroundColor Yellow
}
Write-Host ""

# --- Creeaza voice_bridge\start_voice_auto.bat ---
$batLines = @(
    '@echo off',
    'chcp 65001 >nul',
    'title EMA Voice -- Autostart',
    "set `"EMALOG=$BotDir\data\voice_bridge_autostart.log`"",
    'echo [%date% %time%] ===== autostart EMA pornit ===== >> "%EMALOG%"',
    '',
    'rem Asteapta ~60s (dupa bot/AI) ca reteaua + API-ul local sa fie gata',
    'echo [%date% %time%] astept 60s >> "%EMALOG%"',
    'ping -n 61 127.0.0.1 >nul',
    '',
    "cd /d `"$BotDir`"",
    'echo [%date% %time%] pornesc EMA >> "%EMALOG%"',
    "start `"EMA Voice`" /MIN cmd /c `"`"$PythonExe`" -m voice_bridge >> `"%EMALOG%`" 2>&1`"",
    'echo [%date% %time%] autostart EMA incheiat (lansata detasat) >> "%EMALOG%"',
    'exit /b 0'
)
[System.IO.File]::WriteAllText($BatPath, ($batLines -join "`r`n") + "`r`n", [System.Text.Encoding]::UTF8)
Write-Host "[OK] Creat: voice_bridge\start_voice_auto.bat" -ForegroundColor Green

# --- Task Scheduler: TradingBot-VoiceEMA (neelevat, la login) ---
try {
    $a = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$BatPath`""
    $t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
         -DontStopIfGoingOnBatteries -StartWhenAvailable `
         -ExecutionTimeLimit (New-TimeSpan -Days 2)
    Register-ScheduledTask -TaskName "TradingBot-VoiceEMA" `
        -Action $a -Trigger $t -Settings $s -RunLevel Limited -Force | Out-Null
    Write-Host "[OK] Task TradingBot-VoiceEMA - EMA porneste la login + 60s (neelevat)" -ForegroundColor Green
} catch {
    Write-Host "[EROARE] Task VoiceEMA: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  GATA - la urmatoarea pornire (login):" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Dupa ~60s EMA porneste automat si spune 'EMA este online'."
Write-Host "  Log: data\voice_bridge_autostart.log + data\voice_bridge.log"
Write-Host "  Dezactivare: scripts\remove_autostart_voice.ps1 (ca Administrator)"
Write-Host ""
Read-Host "Apasa Enter pentru iesire"
