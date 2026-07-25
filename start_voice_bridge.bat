@echo off
chcp 65001 >nul
title TradingBot-VoiceBridge-Jarvis
cd /d C:\trading-bot
echo ============================================
echo   Jarvis - Asistent vocal (Trading Bot)
echo   Read-only . Spune "Hey Jarvis" . Ctrl+C = stop
echo ============================================
py -m voice_bridge
echo.
echo Jarvis s-a oprit. Apasa o tasta pentru a inchide.
pause >nul
