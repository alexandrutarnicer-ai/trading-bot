@echo off
chcp 65001 >nul
title TradingBot-TelegramBridge
cd /d C:\trading-bot
echo ============================================
echo   Punte Telegram - Trading Bot
echo   (Ctrl+C pentru oprire)
echo ============================================
py -m telegram_bridge
echo.
echo Puntea s-a oprit. Apasa o tasta pentru a inchide.
pause >nul
