<#
.SYNOPSIS
    Elimina autostart-ul Trading Bot din Windows Task Scheduler.
.NOTES
    IMPORTANT: Trebuie rulat ca Administrator.
    Mod de rulare:
      Win → cauta "PowerShell" → click dreapta → "Run as administrator"
      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
      & "c:\trading-bot\scripts\remove_autostart.ps1"
#>

$BotDir  = Split-Path $PSScriptRoot -Parent
$BatPath = Join-Path $BotDir "live\start_bot.bat"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Trading Bot — Eliminare Autostart" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

$removed = 0

foreach ($taskName in @("TradingBot-MT5", "TradingBot-RunAll")) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
        try {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
            Write-Host "[OK] Task '$taskName' sters" -ForegroundColor Green
            $removed++
        } catch {
            Write-Host "[EROARE] Nu am putut sterge '$taskName': $_" -ForegroundColor Red
            Write-Host "         Incearca manual: Task Scheduler → gaseste task-ul → Delete" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[--] Task '$taskName' nu exista (deja sters sau neinstalat)" -ForegroundColor Gray
    }
}

# Sterge si start_bot.bat daca exista
if (Test-Path $BatPath) {
    try {
        Remove-Item $BatPath -Force
        Write-Host "[OK] Sters: live\start_bot.bat" -ForegroundColor Green
    } catch {
        Write-Host "[--] Nu am putut sterge live\start_bot.bat (nu e critic)" -ForegroundColor Gray
    }
}

Write-Host ""
if ($removed -gt 0) {
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host "  Autostart dezactivat." -ForegroundColor Green
    Write-Host "  La urmatoarea repornire Windows, MT5 si botul" -ForegroundColor Green
    Write-Host "  NU vor mai porni automat." -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Green
} else {
    Write-Host "  Niciun task de sters — autostart-ul nu era activ." -ForegroundColor Yellow
}
Write-Host ""
Read-Host "Apasa Enter pentru iesire"
