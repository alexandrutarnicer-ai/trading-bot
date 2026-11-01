@echo off
chcp 65001 >nul 2>&1
setlocal
title Schimb dispozitiv - PC / laptop
cd /d "%~dp0"

:menu
echo.
echo ============================================================
echo   Schimb dispozitiv (PC / laptop) - branch-ul de date
echo ============================================================
py scripts\device_switch.py status
echo.
echo   1. PREDAU  - plec de pe acest dispozitiv: opresc engine-urile + trimit datele
echo   2. PREIAU  - ajung pe acest dispozitiv: aduc datele + pornesc engine-urile
echo   3. ACTUALIZEZ - doar analiza: aduc datele, NU pornesc nimic
echo   4. TRIMIT  - de pe dispozitivul care ruleaza: trimit datele, engine-urile raman pornite
echo   0. Iesire
echo.
set "CH="
set /p CH="Alege (1/2/3/4/0): "
if "%CH%"=="1" py scripts\device_switch.py predau & goto done
if "%CH%"=="2" py scripts\device_switch.py preiau & goto done
if "%CH%"=="3" py scripts\device_switch.py actualizez & goto done
if "%CH%"=="4" py scripts\device_switch.py trimit & goto done
if "%CH%"=="0" exit /b 0
echo  Optiune invalida.
goto menu

:done
echo.
pause
endlocal
