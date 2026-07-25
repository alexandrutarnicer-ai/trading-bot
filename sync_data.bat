@echo off
chcp 65001 >nul
title Sync date - PUSH (pleci de pe acest dispozitiv)
cd /d C:\trading-bot
echo ============================================
echo   Trimit datele (semnale + tranzactii)
echo   inainte sa treci pe celalalt dispozitiv
echo ============================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\sync_data.ps1"
echo.
pause
