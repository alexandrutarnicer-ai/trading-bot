@echo off
title Trading Bot -- Sesiuni Live
echo ==================================================
echo  Trading Bot -- pornire automata
echo  Astept 45 secunde pentru conectare MT5...
echo ==================================================
timeout /t 45 /nobreak
cd /d "c:\trading-bot"
"C:\Users\alext\AppData\Local\Programs\Python\Python314\python.exe" live\run_all.py
pause
