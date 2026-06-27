<#
.SYNOPSIS
    Instaleaza sau repara winget (Windows Package Manager).
    Apelat automat din setupFirst.bat cand winget nu e gasit in PATH.

    Cazuri acoperite:
    - Windows 11 proaspat instalat (App Installer absent sau neactualizat)
    - Rulare ca Administrator (WindowsApps nu e in PATH in context elevat)
    - Windows 10 fara App Installer
#>

$progressPreference = 'silentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# ── Cazul 1: winget exista dar nu e in PATH (tipic cand rulezi ca Admin) ─────
$wingetPaths = @(
    "$env:LOCALAPPDATA\Microsoft\WindowsApps\winget.exe",
    "$env:ProgramFiles\WindowsApps\Microsoft.DesktopAppInstaller*\winget.exe"
)
foreach ($p in $wingetPaths) {
    $found = Get-Item $p -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
        Write-Host ""
        Write-Host "  [+] winget gasit la: $($found.FullName)" -ForegroundColor Green
        Write-Host "      (nu era in PATH — adaug temporar pentru aceasta sesiune)" -ForegroundColor Gray
        # Adauga in PATH sesiunea curenta
        $env:PATH = "$($found.DirectoryName);$env:PATH"
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            exit 0
        }
    }
}

# ── Cazul 2: winget lipseste complet — trebuie instalat ───────────────────────
$winVer = [System.Environment]::OSVersion.Version
$isWin11 = ($winVer.Major -eq 10 -and $winVer.Build -ge 22000)

Write-Host ""
if ($isWin11) {
    Write-Host "  Windows 11 detectat. Actualizeaz App Installer..." -ForegroundColor Yellow
} else {
    Write-Host "  Windows 10 detectat. Instalez winget complet..." -ForegroundColor Yellow
}
Write-Host ""

$tempDir = Join-Path $env:TEMP "winget_setup_tradingbot"
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

# ── Pe Windows 10: descarca si instaleaza dependentele ───────────────────────
if (-not $isWin11) {
    Write-Host "  [1/3] Microsoft VCLibs (Visual C++ Runtime)..." -ForegroundColor Yellow
    try {
        $vcFile = Join-Path $tempDir "VCLibs.appx"
        Invoke-WebRequest "https://aka.ms/Microsoft.VCLibs.x64.14.00.Desktop.appx" `
            -OutFile $vcFile -UseBasicParsing -TimeoutSec 60
        Add-AppxPackage $vcFile -ErrorAction SilentlyContinue
        Write-Host "        OK" -ForegroundColor Green
    } catch {
        Write-Host "        WARN: $($_.Exception.Message)" -ForegroundColor DarkYellow
    }

    Write-Host "  [2/3] Microsoft UI.Xaml 2.8..." -ForegroundColor Yellow
    try {
        $xamlFile = Join-Path $tempDir "UIXaml.appx"
        Invoke-WebRequest "https://github.com/microsoft/microsoft-ui-xaml/releases/download/v2.8.6/Microsoft.UI.Xaml.2.8.x64.appx" `
            -OutFile $xamlFile -UseBasicParsing -TimeoutSec 60
        Add-AppxPackage $xamlFile -ErrorAction SilentlyContinue
        Write-Host "        OK" -ForegroundColor Green
    } catch {
        Write-Host "        WARN: $($_.Exception.Message)" -ForegroundColor DarkYellow
    }

    Write-Host "  [3/3] winget (App Installer)..." -ForegroundColor Yellow
} else {
    Write-Host "  [1/1] winget (App Installer)..." -ForegroundColor Yellow
}

# ── Descarca si instaleaza winget ─────────────────────────────────────────────
try {
    $wingetFile = Join-Path $tempDir "winget.msixbundle"
    Invoke-WebRequest "https://github.com/microsoft/winget-cli/releases/latest/download/Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle" `
        -OutFile $wingetFile -UseBasicParsing -TimeoutSec 120
    Add-AppxPackage $wingetFile -ForceApplicationShutdown
    Write-Host "        OK" -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "  [!] Instalare esuata: $($_.Exception.Message)" -ForegroundColor Red
    Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    exit 1
}

Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue

# ── Refresh PATH si verificare finala ─────────────────────────────────────────
$userPath    = [System.Environment]::GetEnvironmentVariable("PATH", "User")
$machinePath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
$env:PATH    = "$userPath;$machinePath"

# Cauta si in WindowsApps explicit (util cand rulezi ca admin)
$wingetExe = Get-Item "$env:LOCALAPPDATA\Microsoft\WindowsApps\winget.exe" -ErrorAction SilentlyContinue
if ($wingetExe) {
    $env:PATH = "$($wingetExe.DirectoryName);$env:PATH"
}

if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host ""
    Write-Host "  [+] winget instalat si activ!" -ForegroundColor Green
    exit 0
} else {
    Write-Host ""
    Write-Host "  [~] winget instalat — necesita repornire CMD pentru activare." -ForegroundColor Yellow
    exit 2
}
