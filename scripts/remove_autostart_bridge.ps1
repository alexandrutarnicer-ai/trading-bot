<#
.SYNOPSIS
    Dezactiveaza pornirea automata a Puntii Telegram.
    Sterge task-ul TradingBot-TelegramBridge din Task Scheduler.

.NOTES
    Trebuie rulat ca Administrator. Nu opreste puntea daca ruleaza acum
    (foloseste butonul Stop din UI sau Ctrl+C in fereastra ei) - doar impiedica
    pornirea automata la urmatorul login. Scriptul e pur ASCII (CP1252-safe).
#>

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Punte Telegram - Dezactivare Autostart" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

try {
    if (Get-ScheduledTask -TaskName "TradingBot-TelegramBridge" -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName "TradingBot-TelegramBridge" -Confirm:$false
        Write-Host "[OK] Task TradingBot-TelegramBridge sters." -ForegroundColor Green
    } else {
        Write-Host "[INFO] Task-ul TradingBot-TelegramBridge nu exista (deja dezactivat)." -ForegroundColor Yellow
    }
} catch {
    Write-Host "[EROARE] $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "  Puntea NU mai porneste automat la login."
Write-Host "  O poti porni oricand manual: start_telegram_bridge.bat sau butonul din UI."
Write-Host ""
Read-Host "Apasa Enter pentru iesire"
