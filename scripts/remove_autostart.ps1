<#
.SYNOPSIS
    Elimina autostart-ul Trading Bot din Windows Task Scheduler.
.NOTES
    IMPORTANT: Trebuie rulat ca Administrator.
    Mod de rulare:
      Win -> cauta "PowerShell" -> click dreapta -> "Run as administrator"
      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
      & "c:\trading-bot\scripts\remove_autostart.ps1"
#>

$BotDir  = Split-Path $PSScriptRoot -Parent
$BatPath = Join-Path $BotDir "live\start_bot.bat"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Trading Bot - Eliminare Autostart" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

$removed = 0

# Task-ul propriu al botului pe reguli
$task = Get-ScheduledTask -TaskName "TradingBot-RunAll" -ErrorAction SilentlyContinue
if ($task) {
    try {
        Unregister-ScheduledTask -TaskName "TradingBot-RunAll" -Confirm:$false
        Write-Host "[OK] Task TradingBot-RunAll sters" -ForegroundColor Green
        $removed++
    } catch {
        Write-Host "[EROARE] Nu am putut sterge TradingBot-RunAll : $_" -ForegroundColor Red
        Write-Host "         Incearca manual: Task Scheduler -> gaseste task-ul -> Delete" -ForegroundColor Yellow
    }
} else {
    Write-Host "[--] Task TradingBot-RunAll nu exista (deja sters sau neinstalat)" -ForegroundColor Gray
}

# MT5 partajat — sterge DOAR daca motorul AI (TradingBot-AIEngine) nu-l mai
# foloseste. Altfel autostart-ul AI ar ramane fara MT5 la pornire.
$aiStillUsesMt5 = [bool](Get-ScheduledTask -TaskName "TradingBot-AIEngine" -ErrorAction SilentlyContinue)
if ($aiStillUsesMt5) {
    Write-Host "[--] Task TradingBot-MT5 pastrat (motorul AI TradingBot-AIEngine inca il foloseste)" -ForegroundColor Yellow
} else {
    $mt5Task = Get-ScheduledTask -TaskName "TradingBot-MT5" -ErrorAction SilentlyContinue
    if ($mt5Task) {
        try {
            Unregister-ScheduledTask -TaskName "TradingBot-MT5" -Confirm:$false
            Write-Host "[OK] Task TradingBot-MT5 sters (niciun engine nu-l mai foloseste)" -ForegroundColor Green
            $removed++
        } catch {
            Write-Host "[EROARE] Nu am putut sterge TradingBot-MT5 : $_" -ForegroundColor Red
        }
    } else {
        Write-Host "[--] Task TradingBot-MT5 nu exista (deja sters sau neinstalat)" -ForegroundColor Gray
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
    Write-Host "  Niciun task de sters - autostart-ul nu era activ." -ForegroundColor Yellow
}
Write-Host ""
Read-Host "Apasa Enter pentru iesire"
