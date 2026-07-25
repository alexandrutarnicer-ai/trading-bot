<#
.SYNOPSIS
    Sincronizeaza DOAR datele (semnale + tranzactii) intre dispozitive (PC <-> laptop).
    Comita si trimite pe branch-ul curent DOAR daca exista date noi. NU ruleaza pe 'main'
    (acolo datele sunt ignorate — cod curat, un singur dispozitiv).

.DESCRIPTION
    Transfera intre dispozitive:
      - Botul pe reguli:  data/live_signals/*/signals.csv, outcomes.csv, ai_filter.jsonl
      - Motorul AI:       data/ai/ai_outcomes.csv  (tranzactiile INCHISE, exportate din ledger)
    NU transfera: state.pkl, generator.log, ledger.db (stare/loguri per-masina; pozitiile
    deschise se reconciliaza oricum din MT5 dupa magic, nu din fisiere).

.PARAMETER Pull
    In loc sa comita+trimita (cand PLECI de pe un dispozitiv), aduce datele de pe celalalt
    dispozitiv (cand AJUNGI). Foloseste-l inainte sa pornesti motoarele pe noul dispozitiv.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\sync_data.ps1          # comit + push (pleci)
    powershell -ExecutionPolicy Bypass -File scripts\sync_data.ps1 -Pull    # pull (ajungi)
#>

param([switch]$Pull)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

function Fail($msg) { Write-Host "[EROARE] $msg" -ForegroundColor Red; exit 1 }

# Branch curent — refuza 'main' (datele nu se comit acolo)
$branch = (& git rev-parse --abbrev-ref HEAD 2>$null)
if (-not $branch) { Fail "Nu sunt intr-un repo git." }
$branch = $branch.Trim()

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Sync date  -  branch: $branch  -  $(if ($Pull) {'PULL'} else {'PUSH'})" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

if ($branch -eq "main") {
    Fail "Esti pe 'main' — datele sunt IGNORATE aici. Comuta pe branch-ul live (ex: git checkout alex-live)."
}

# ── Mod PULL: adu datele de pe celalalt dispozitiv (cand ajungi) ──
if ($Pull) {
    Write-Host "[PULL] Aduc datele de pe origin/$branch ..." -ForegroundColor Yellow
    & git pull --no-edit origin $branch
    if ($LASTEXITCODE -ne 0) { Fail "Pull esuat (conflict? verifica manual)." }
    Write-Host "[OK] La zi cu celalalt dispozitiv. Poti porni motoarele." -ForegroundColor Green
    exit 0
}

# ── Mod PUSH (implicit): comit + trimit datele acestui dispozitiv ──
# Aduna DOAR fisierele de date dorite (nu state.pkl / generator.log)
$data = @()
if (Test-Path "data/live_signals") {
    $data += Get-ChildItem -Path "data/live_signals" -Recurse -File -Include *.csv, *.jsonl -ErrorAction SilentlyContinue
}
if (Test-Path "data/ai/ai_outcomes.csv") { $data += Get-Item "data/ai/ai_outcomes.csv" }

if ($data.Count -eq 0) {
    Write-Host "[INFO] Niciun fisier de date gasit. Nimic de sincronizat." -ForegroundColor Yellow
    exit 0
}

# Force-add (live_signals e gitignored); ai_outcomes.csv e un-ignored
& git add -f -- $data.FullName

# Ceva de comis?
& git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "[INFO] Nicio schimbare fata de ultima sincronizare. Nimic de trimis." -ForegroundColor Yellow
    exit 0
}

$n = (& git diff --cached --name-only).Count
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
& git commit -m "data sync ($env:COMPUTERNAME $stamp) - $n fisiere" | Out-Null
Write-Host "[OK] Comis $n fisiere de date." -ForegroundColor Green

# Integreaza eventualele date de pe celalalt dispozitiv, apoi push
Write-Host "[SYNC] Integrez remote (daca exista) si trimit ..." -ForegroundColor Yellow
& git pull --no-edit origin $branch 2>$null
if ($LASTEXITCODE -ne 0) {
    Fail "Merge cu remote a esuat (conflict de date?). Rezolva manual, apoi 'git push'."
}
& git push origin $branch
if ($LASTEXITCODE -ne 0) {
    Fail "Push esuat - verifica contul GitHub (alege 'alexandrutarnicer-ai') sau conexiunea."
}
Write-Host "[OK] Date trimise pe origin/$branch. Poti trece pe celalalt dispozitiv." -ForegroundColor Green
