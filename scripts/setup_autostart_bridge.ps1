<#
.SYNOPSIS
    Configureaza pornirea automata a Puntii Telegram la startup Windows.
    Creeaza un singur task: TradingBot-TelegramBridge (daemon standalone, aditiv).

.NOTES
    IMPORTANT: Trebuie rulat ca Administrator.
      Win -> cauta "PowerShell" -> click dreapta -> "Run as administrator"
      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
      & "c:\trading-bot\scripts\setup_autostart_bridge.ps1"

    Puntea NU are nevoie de MT5 sau Ollama (proces separat, doar citeste stare +
    API local). Are nevoie doar de Python + de configurarea Telegram (token+chat_id,
    salvate din UI in data\telegram_config.json). Task-ul ruleaza NEELEVAT
    (-RunLevel Limited) ca UI-ul neelevat sa il poata opri (vezi setup_autostart.ps1).
    Scriptul e pur ASCII (Windows PowerShell 5.1 il citeste CP1252).
#>

$BotDir  = Split-Path $PSScriptRoot -Parent
$BatPath = Join-Path $BotDir "telegram_bridge\start_bridge_auto.bat"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Punte Telegram - Setup Autostart" -ForegroundColor Cyan
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

# Avertisment daca Telegram nu pare configurat (puntea nu porneste fara token+chat_id)
$tgCfg = Join-Path $BotDir "data\telegram_config.json"
if (-not (Test-Path $tgCfg)) {
    Write-Host "  [ATENTIE] data\telegram_config.json lipseste - configureaza Telegram din UI" -ForegroundColor Yellow
    Write-Host "            inainte ca puntea sa poata porni." -ForegroundColor Yellow
}
Write-Host ""

# --- Creeaza telegram_bridge\start_bridge_auto.bat ---
# Linii Telegram: fallback din registry (puntea citeste oricum data\telegram_config.json)
$tgLine1 = 'for /f "delims=" %%i in (''powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable(\"TELEGRAM_TOKEN\",\"User\")"'') do set "TELEGRAM_TOKEN=%%i"'
$tgLine2 = 'for /f "delims=" %%i in (''powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable(\"TELEGRAM_CHAT_ID\",\"User\")"'') do set "TELEGRAM_CHAT_ID=%%i"'

$batLines = @(
    '@echo off',
    'chcp 65001 >nul',
    'title Telegram Bridge -- Autostart',
    "set `"BRLOG=$BotDir\data\telegram_bridge_autostart.log`"",
    'echo [%date% %time%] ===== autostart punte pornit ===== >> "%BRLOG%"',
    '',
    'rem Fallback Telegram din registry (User scope) - puntea citeste si data\telegram_config.json',
    $tgLine1,
    $tgLine2,
    '',
    'rem Asteapta ~60s (dupa bot/AI) ca reteaua + API-ul local sa fie gata',
    'echo [%date% %time%] astept 60s >> "%BRLOG%"',
    'ping -n 61 127.0.0.1 >nul',
    '',
    "cd /d `"$BotDir`"",
    'echo [%date% %time%] pornesc puntea >> "%BRLOG%"',
    "start `"Telegram Bridge`" /MIN cmd /c `"`"$PythonExe`" -m telegram_bridge >> `"%BRLOG%`" 2>&1`"",
    'echo [%date% %time%] autostart punte incheiat (lansata detasat) >> "%BRLOG%"',
    'exit /b 0'
)
[System.IO.File]::WriteAllText($BatPath, ($batLines -join "`r`n") + "`r`n", [System.Text.Encoding]::UTF8)
Write-Host "[OK] Creat: telegram_bridge\start_bridge_auto.bat" -ForegroundColor Green

# --- Task Scheduler: TradingBot-TelegramBridge (neelevat, la login) ---
try {
    $a = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$BatPath`""
    $t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
         -DontStopIfGoingOnBatteries -StartWhenAvailable `
         -ExecutionTimeLimit (New-TimeSpan -Days 2)
    Register-ScheduledTask -TaskName "TradingBot-TelegramBridge" `
        -Action $a -Trigger $t -Settings $s -RunLevel Limited -Force | Out-Null
    Write-Host "[OK] Task TradingBot-TelegramBridge - puntea porneste la login + 60s (neelevat)" -ForegroundColor Green
} catch {
    Write-Host "[EROARE] Task TelegramBridge: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  GATA - la urmatoarea pornire (login):" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Dupa ~60s puntea Telegram porneste automat si iti trimite un mesaj."
Write-Host "  Log: data\telegram_bridge_autostart.log + data\telegram_bridge.log"
Write-Host "  Dezactivare: scripts\remove_autostart_bridge.ps1 (ca Administrator)"
Write-Host ""
Read-Host "Apasa Enter pentru iesire"
