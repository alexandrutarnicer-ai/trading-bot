<#
.SYNOPSIS
    Instaleaza winget (Windows Package Manager) daca lipseste.
    Descarca dependentele necesare si pachetul principal de pe Microsoft/GitHub.
    Apelat automat din setupFirst.bat.
#>

$progressPreference = 'silentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Verifica daca winget e deja disponibil
if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host "  [+] winget deja disponibil." -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "  Instalez winget (Windows Package Manager)..." -ForegroundColor Yellow
Write-Host "  Descarc ~30 MB — poate dura 1-2 minute..." -ForegroundColor Gray
Write-Host ""

$tempDir = Join-Path $env:TEMP "winget_setup_tradingbot"
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

# ── 1. Microsoft.VCLibs (Visual C++ Runtime) ─────────────────────────────────
Write-Host "  [1/3] Microsoft VCLibs..." -ForegroundColor Yellow
try {
    $vcFile = Join-Path $tempDir "VCLibs.appx"
    Invoke-WebRequest "https://aka.ms/Microsoft.VCLibs.x64.14.00.Desktop.appx" `
        -OutFile $vcFile -UseBasicParsing -TimeoutSec 60
    Add-AppxPackage $vcFile -ErrorAction SilentlyContinue
    Write-Host "        OK" -ForegroundColor Green
} catch {
    Write-Host "        WARN: $($_.Exception.Message) (poate fi deja instalat)" -ForegroundColor DarkYellow
}

# ── 2. Microsoft.UI.Xaml 2.8 (cerut de winget 1.7+) ─────────────────────────
Write-Host "  [2/3] Microsoft UI.Xaml 2.8..." -ForegroundColor Yellow
try {
    $xamlFile = Join-Path $tempDir "UIXaml.appx"
    Invoke-WebRequest "https://github.com/microsoft/microsoft-ui-xaml/releases/download/v2.8.6/Microsoft.UI.Xaml.2.8.x64.appx" `
        -OutFile $xamlFile -UseBasicParsing -TimeoutSec 60
    Add-AppxPackage $xamlFile -ErrorAction SilentlyContinue
    Write-Host "        OK" -ForegroundColor Green
} catch {
    Write-Host "        WARN: $($_.Exception.Message) (poate fi deja instalat)" -ForegroundColor DarkYellow
}

# ── 3. winget (App Installer) ─────────────────────────────────────────────────
Write-Host "  [3/3] winget (App Installer)..." -ForegroundColor Yellow
try {
    $wingetFile = Join-Path $tempDir "winget.msixbundle"
    Invoke-WebRequest "https://github.com/microsoft/winget-cli/releases/latest/download/Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle" `
        -OutFile $wingetFile -UseBasicParsing -TimeoutSec 120
    Add-AppxPackage $wingetFile
    Write-Host "        OK" -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "  [!] Instalare winget esuata: $($_.Exception.Message)" -ForegroundColor Red
    Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    exit 1
}

# Cleanup fisiere temporare
Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue

# Refresh PATH in sesiunea curenta (winget e in WindowsApps, de obicei deja in PATH)
$userPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
$machinePath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
$env:PATH = "$userPath;$machinePath"

# Verificare finala
if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host ""
    Write-Host "  [+] winget instalat cu succes!" -ForegroundColor Green
    exit 0
} else {
    Write-Host ""
    Write-Host "  [~] winget instalat dar necesita o repornire CMD pentru activare." -ForegroundColor Yellow
    exit 2  # cod special: instalat dar PATH nu e inca activ
}
