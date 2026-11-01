@echo off
chcp 65001 >nul
title Sync PC / laptop - cod + date (alex-live)
cd /d "%~dp0"
:: Acelasi script pe ambele dispozitive: trimite datele engine-urilor care au rulat aici,
:: aduce codul + datele celuilalt, trimite tot pe GitHub. Nu porneste / opreste nimic.
py scripts\sync_branch.py
pause
