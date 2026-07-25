@echo off
chcp 65001 >nul
title Sync date - PULL (ajungi pe acest dispozitiv)
cd /d C:\trading-bot
echo ============================================
echo   Aduc datele de pe celalalt dispozitiv
echo   INAINTE sa pornesti botul / motorul AI
echo ============================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\sync_data.ps1" -Pull
echo.
pause
