<#
.SYNOPSIS
    Setup automat Trading Bot - ruleaza o singura data pe un calculator nou.
.EXAMPLE
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    .\scripts\setup_instance.ps1
#>

$ErrorActionPreference = "Stop"
$ROOT = Split-Path $PSScriptRoot -Parent

Write-Host ""
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "  Trading Bot - Setup instanta noua" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Verifica Python
Write-Host "[1/5] Verific Python..." -ForegroundColor Yellow

$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 10) {
                $pythonCmd = $cmd
                Write-Host "    OK: $ver" -ForegroundColor Green
                break
            } else {
                Write-Host "    WARN: $ver gasit, dar necesar >= 3.10" -ForegroundColor Yellow
            }
        }
    } catch {}
}

if (-not $pythonCmd) {
    Write-Host ""
    Write-Host "  EROARE: Python 3.10+ nu a fost gasit." -ForegroundColor Red
    Write-Host "  Descarca de la: https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "  Bifeaza 'Add Python to PATH' la instalare." -ForegroundColor Red
    exit 1
}

# 2. Verifica Node.js
Write-Host "[2/5] Verific Node.js..." -ForegroundColor Yellow

try {
    $nodeVer = node --version 2>&1
    if ($nodeVer -match "v(\d+)") {
        $nodeMajor = [int]$Matches[1]
        if ($nodeMajor -ge 18) {
            Write-Host "    OK: Node.js $nodeVer" -ForegroundColor Green
        } else {
            Write-Host "  EROARE: Node.js $nodeVer gasit, dar necesar >= v18." -ForegroundColor Red
            Write-Host "  Descarca de la: https://nodejs.org/" -ForegroundColor Red
            exit 1
        }
    }
} catch {
    Write-Host "  EROARE: Node.js nu a fost gasit." -ForegroundColor Red
    Write-Host "  Descarca de la: https://nodejs.org/ (versiunea LTS)" -ForegroundColor Red
    exit 1
}

# 3. Instaleaza dependente Python
Write-Host "[3/5] Instalez dependente Python (pip install)..." -ForegroundColor Yellow

Set-Location $ROOT
& $pythonCmd -m pip install -r requirements.txt --quiet --upgrade
if ($LASTEXITCODE -ne 0) {
    Write-Host "  EROARE la pip install. Verifica conexiunea la internet." -ForegroundColor Red
    exit 1
}
Write-Host "    OK: pachete Python instalate" -ForegroundColor Green

# 4. Instaleaza dependente frontend
Write-Host "[4/5] Instalez dependente frontend (npm install)..." -ForegroundColor Yellow

Set-Location (Join-Path $ROOT "frontend")
npm install --silent
if ($LASTEXITCODE -ne 0) {
    Write-Host "  EROARE la npm install." -ForegroundColor Red
    exit 1
}
Write-Host "    OK: pachete npm instalate" -ForegroundColor Green
Set-Location $ROOT

# 5. Creeaza directoare de date
Write-Host "[5/5] Creez directoare necesare..." -ForegroundColor Yellow

$dirs = @(
    "data",
    "data\profiles",
    "data\live_signals\session1",
    "data\live_signals\session2",
    "data\live_signals\session3",
    "data\live_signals\session4",
    "data\live_signals\session5",
    "data\live_signals\session6"
)

foreach ($d in $dirs) {
    $path = Join-Path $ROOT $d
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
        Write-Host "    Creat: $d" -ForegroundColor Gray
    }
}

$stdProfile = Join-Path $ROOT "data\profiles\standard.json"
if (-not (Test-Path $stdProfile)) {
    $ts = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    $profileJson = '{"id":"standard","name":"Standard Profile","description":"Configuratia implicita","start_balance":1000,"sessions":[],"updated_at":"' + $ts + '"}'
    $profileJson | Out-File -FilePath $stdProfile -Encoding utf8
    Write-Host "    Creat: data/profiles/standard.json" -ForegroundColor Gray
} else {
    Write-Host "    OK: data/profiles/standard.json exista deja" -ForegroundColor Green
}

Write-Host ""
Write-Host "=================================================" -ForegroundColor Green
Write-Host "  Setup complet!" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Pasi urmatori:" -ForegroundColor Cyan
Write-Host "  1. Deschide MetaTrader 5 si conecteaza-te pe cont demo" -ForegroundColor White
Write-Host "  2. Ruleaza start_app.ps1 pentru a porni aplicatia:" -ForegroundColor White
Write-Host ""
Write-Host "     Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass" -ForegroundColor Gray
Write-Host "     .\start_app.ps1" -ForegroundColor Gray
Write-Host ""
Write-Host "  Acces: http://localhost:5173" -ForegroundColor Cyan
Write-Host ""
