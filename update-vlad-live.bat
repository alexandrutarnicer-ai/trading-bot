@echo off
chcp 65001 >nul 2>&1
setlocal
set "ROOT=%~dp0"
set "GITROOT=%ROOT:~0,-1%"
title Update vlad-live from main

echo.
echo ============================================================
echo   Update vlad-live from origin/main
echo ============================================================
echo.

git --version >nul 2>&1
if errorlevel 1 (
    echo  [!] Git is not installed or is not in PATH.
    pause
    exit /b 1
)

for /f %%B in ('git -C "%GITROOT%" branch --show-current 2^>nul') do set "BRANCH=%%B"
if not "%BRANCH%"=="vlad-live" (
    echo  [!] Switch to the vlad-live branch before running this updater.
    echo      Current branch: %BRANCH%
    pause
    exit /b 1
)

set "DIRTY="
for /f "usebackq delims=" %%A in (`git -C "%GITROOT%" status --porcelain`) do set "DIRTY=1"
if defined DIRTY (
    echo  [!] The working tree has local changes. Commit or stash them first.
    echo      This updater will not overwrite local work.
    pause
    exit /b 1
)

echo  Fetching origin/main ...
git -C "%GITROOT%" fetch origin main
if errorlevel 1 (
    echo  [!] Fetch failed. Check your network connection and try again.
    pause
    exit /b 1
)

echo.
echo  Fast-forwarding vlad-live from origin/main ...
git -C "%GITROOT%" merge --ff-only origin/main
if errorlevel 1 (
    echo.
    echo  [!] Fast-forward failed. Resolve the branch history manually.
    pause
    exit /b 1
)

echo.
echo  vlad-live is up to date with origin/main.
echo  Push the branch with: git push -u origin vlad-live
echo.
pause
endlocal
