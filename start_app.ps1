<#
.SYNOPSIS
    Porneste API backend + frontend React pentru Trading Bot.
.DESCRIPTION
    Deschide doua ferestre PowerShell separate si browserul la http://localhost:5173
    Botul live se porneste din interfata web (butonul Start din Dashboard).
.EXAMPLE
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    .\start_app.ps1
#>

$ROOT = $PSScriptRoot

$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3\.(\d+)" -and [int]$Matches[1] -ge 10) {
            $pythonCmd = $cmd
            break
        }
    } catch {}
}

if (-not $pythonCmd) {
    Write-Host "EROARE: Python 3.10+ nu a fost gasit." -ForegroundColor Red
    Write-Host "Ruleaza mai intai: .\scripts\setup_instance.ps1" -ForegroundColor Yellow
    Read-Host "Apasa Enter pentru a inchide"
    exit 1
}

Write-Host ""
Write-Host "  Trading Bot - Pornire aplicatie" -ForegroundColor Cyan
Write-Host ""

# API backend
Write-Host "  [1/2] Pornesc API backend (port 8000)..." -ForegroundColor Yellow
$apiScript = "cd '$ROOT'; Write-Host 'API Trading Bot - port 8000' -ForegroundColor Cyan; $pythonCmd api/main.py"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiScript -WindowStyle Normal

Start-Sleep -Seconds 2

# Frontend
Write-Host "  [2/2] Pornesc frontend React (port 5173)..." -ForegroundColor Yellow
$frontScript = "cd '$ROOT\frontend'; Write-Host 'Frontend React - port 5173' -ForegroundColor Cyan; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontScript -WindowStyle Normal

Start-Sleep -Seconds 3

# Browser
Write-Host "  Deschid browserul..." -ForegroundColor Green
Start-Process "http://localhost:5173"

Write-Host ""
Write-Host "  Aplicatia ruleaza in ferestrele PowerShell deschise." -ForegroundColor Green
Write-Host "  Inchide acele ferestre pentru a opri aplicatia." -ForegroundColor Gray
Write-Host ""
