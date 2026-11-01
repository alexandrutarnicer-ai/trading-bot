@echo off
chcp 65001 >nul
title Sync date - ACTUALIZEZ (aduc datele, fara sa pornesc engine-uri)
cd /d "%~dp0"
:: Inlocuit de schimb_dispozitiv.bat (predare / preluare completa). Aici: ACTUALIZEZ = aduce
:: datele celuilalt dispozitiv; fisierele locale care s-ar suprascrie merg in data\_sync_backup\.
py scripts\device_switch.py actualizez
pause
