<#
.SYNOPSIS
    Dezactiveaza autostart-ul GENERIC al unui engine (pereche cu setup_autostart_engine.ps1).
    Sterge task-ul TradingBot-<Nume>; task-ul PARTAJAT TradingBot-MT5 e sters DOAR daca niciun
    alt engine (RunAll / AIEngine / DailyEngine) nu-l mai foloseste.

.NOTES
    Nu opreste engine-ul daca ruleaza acum (foloseste Stop din UI) - doar pornirea la login.
    Scriptul e pur ASCII (CP1252-safe).
#>
param([Parameter(Mandatory = $true)][string]$Engine)

$TASKS = @{ "daily" = "TradingBot-DailyEngine" }
$BATS  = @{ "daily" = "daily_engine\start_daily_engine_auto.bat" }
if (-not $TASKS.ContainsKey($Engine)) {
    Write-Host "[EROARE] Engine necunoscut: $Engine" -ForegroundColor Red
    Read-Host "Apasa Enter pentru iesire"
    exit 1
}
$Task   = $TASKS[$Engine]
$BotDir = Split-Path $PSScriptRoot -Parent

if (Get-ScheduledTask -TaskName $Task -ErrorAction SilentlyContinue) {
    try {
        Unregister-ScheduledTask -TaskName $Task -Confirm:$false
        Write-Host "[OK] Task $Task sters" -ForegroundColor Green
    } catch {
        Write-Host "[EROARE] Nu am putut sterge $Task : $_" -ForegroundColor Red
    }
} else {
    Write-Host "[--] Task $Task nu exista (deja dezactivat)" -ForegroundColor Gray
}

$users = @("TradingBot-RunAll", "TradingBot-AIEngine", "TradingBot-DailyEngine") |
         Where-Object { $_ -ne $Task -and (Get-ScheduledTask -TaskName $_ -ErrorAction SilentlyContinue) }
if ($users) {
    Write-Host "[--] Task TradingBot-MT5 pastrat (inca folosit de: $($users -join ', '))" -ForegroundColor Yellow
} elseif (Get-ScheduledTask -TaskName "TradingBot-MT5" -ErrorAction SilentlyContinue) {
    try {
        Unregister-ScheduledTask -TaskName "TradingBot-MT5" -Confirm:$false
        Write-Host "[OK] Task TradingBot-MT5 sters (niciun engine nu-l mai foloseste)" -ForegroundColor Green
    } catch {
        Write-Host "[EROARE] Nu am putut sterge TradingBot-MT5 : $_" -ForegroundColor Red
    }
}

$bat = Join-Path $BotDir $BATS[$Engine]
if (Test-Path $bat) { Remove-Item $bat -Force; Write-Host "[OK] Sters $($BATS[$Engine])" -ForegroundColor Green }

Write-Host ""
Read-Host "Apasa Enter pentru iesire"
