@echo off
chcp 65001 >nul
title Sync date - TRIMIT (de pe dispozitivul care ruleaza engine-urile)
cd /d "%~dp0"
:: Inlocuit de schimb_dispozitiv.bat (predare / preluare completa). Aici: TRIMIT = datele
:: (inclusiv ledger-ul AI, copie consistenta) fara sa opreasca engine-urile.
py scripts\device_switch.py trimit
pause
