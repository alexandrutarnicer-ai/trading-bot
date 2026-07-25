<#
.SYNOPSIS
    Dezactiveaza pornirea automata a lui EMA (asistentul vocal).
    Sterge task-ul TradingBot-VoiceEMA din Task Scheduler.

.NOTES
    Trebuie rulat ca Administrator. Nu opreste EMA daca ruleaza acum (foloseste
    butonul Stop din UI sau Ctrl+C in fereastra ei) - doar impiedica pornirea
    automata la urmatorul login. Scriptul e pur ASCII (CP1252-safe).
#>

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  EMA (asistent vocal) - Dezactivare Autostart" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

try {
    if (Get-ScheduledTask -TaskName "TradingBot-VoiceEMA" -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName "TradingBot-VoiceEMA" -Confirm:$false
        Write-Host "[OK] Task TradingBot-VoiceEMA sters." -ForegroundColor Green
    } else {
        Write-Host "[INFO] Task-ul TradingBot-VoiceEMA nu exista (deja dezactivat)." -ForegroundColor Yellow
    }
} catch {
    Write-Host "[EROARE] $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "  EMA NU mai porneste automat la login."
Write-Host "  O poti porni oricand manual: start_voice_bridge.bat sau butonul din UI."
Write-Host ""
Read-Host "Apasa Enter pentru iesire"
