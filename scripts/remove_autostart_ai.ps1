<#
.SYNOPSIS
    Elimina autostart-ul AI Engine din Windows Task Scheduler.
.NOTES
    IMPORTANT: Trebuie rulat ca Administrator.
    Mod de rulare:
      Win -> cauta "PowerShell" -> click dreapta -> "Run as administrator"
      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
      & "c:\trading-bot\scripts\remove_autostart_ai.ps1"

    ALINIERE: task-ul TradingBot-MT5 e PARTAJAT cu botul pe reguli. Il stergem
    DOAR daca botul (TradingBot-RunAll) NU mai are autostart activ - altfel
    botul ar ramane fara MT5 la pornire.
#>

$BotDir  = Split-Path $PSScriptRoot -Parent
$BatPath = Join-Path $BotDir "ai_engine\start_ai_engine_auto.bat"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  AI Engine - Eliminare Autostart" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

$removed = 0

# 1. Task-ul propriu al motorului AI
$task = Get-ScheduledTask -TaskName "TradingBot-AIEngine" -ErrorAction SilentlyContinue
if ($task) {
    try {
        Unregister-ScheduledTask -TaskName "TradingBot-AIEngine" -Confirm:$false
        Write-Host "[OK] Task TradingBot-AIEngine sters" -ForegroundColor Green
        $removed++
    } catch {
        Write-Host "[EROARE] Nu am putut sterge TradingBot-AIEngine : $_" -ForegroundColor Red
    }
} else {
    Write-Host "[--] Task TradingBot-AIEngine nu exista (deja sters sau neinstalat)" -ForegroundColor Gray
}

# 2. MT5 partajat - sterge DOAR daca botul nu-l mai foloseste
$botStillUsesMt5 = [bool](Get-ScheduledTask -TaskName "TradingBot-RunAll" -ErrorAction SilentlyContinue)
if ($botStillUsesMt5) {
    Write-Host "[--] Task TradingBot-MT5 pastrat (botul TradingBot-RunAll inca il foloseste)" -ForegroundColor Yellow
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
        Write-Host "[--] Task TradingBot-MT5 nu exista" -ForegroundColor Gray
    }
}

# 3. Sterge si start_ai_engine_auto.bat daca exista
if (Test-Path $BatPath) {
    try {
        Remove-Item $BatPath -Force
        Write-Host "[OK] Sters: ai_engine\start_ai_engine_auto.bat" -ForegroundColor Green
    } catch {
        Write-Host "[--] Nu am putut sterge start_ai_engine_auto.bat (nu e critic)" -ForegroundColor Gray
    }
}

Write-Host ""
if ($removed -gt 0) {
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host "  Autostart AI Engine dezactivat." -ForegroundColor Green
    Write-Host "  La urmatoarea repornire Windows, motorul AI" -ForegroundColor Green
    Write-Host "  NU va mai porni automat." -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Green
} else {
    Write-Host "  Niciun task de sters - autostart-ul AI nu era activ." -ForegroundColor Yellow
}
Write-Host ""
Read-Host "Apasa Enter pentru iesire"
