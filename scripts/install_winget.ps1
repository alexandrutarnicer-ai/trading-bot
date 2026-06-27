# install_winget.ps1
# Instaleaza winget (Windows Package Manager) daca lipseste.
# Apelat automat din setupFirst.bat.

$progressPreference = 'silentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Cazul 1: winget exista dar nu e in PATH (tipic rulare ca Admin pe Win11)
$wingetExe = Get-Item "$env:LOCALAPPDATA\Microsoft\WindowsApps\winget.exe" -ErrorAction SilentlyContinue
if ($wingetExe) {
    $env:PATH = "$($wingetExe.DirectoryName);$env:PATH"
    Write-Host "  [+] winget gasit - adaugat in PATH." -ForegroundColor Green
    exit 0
}

# Detectie Windows 11 via registry (sigura in PS 5.1, spre deosebire de OSVersion)
$buildNum = 0
try {
    $buildNum = [int](Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion").CurrentBuildNumber
} catch {}
$isWin11 = ($buildNum -ge 22000)

Write-Host ""
Write-Host "  Instalez winget (build OS: $buildNum)..." -ForegroundColor Yellow

# Temp dir robust - GetTempPath() nu depinde de env:TEMP
$tempBase = [System.IO.Path]::GetTempPath()
if (-not $tempBase -or -not (Test-Path $tempBase)) {
    $tempBase = "C:\Windows\Temp"
}
$tempDir = Join-Path $tempBase "winget_tradingbot"
New-Item -ItemType Directory -Force -Path $tempDir -ErrorAction SilentlyContinue | Out-Null

if (-not (Test-Path $tempDir)) {
    Write-Host "  [!] Nu pot crea directorul temporar: $tempDir" -ForegroundColor Red
    exit 1
}

Write-Host "  Temp: $tempDir" -ForegroundColor DarkGray
Write-Host ""

# Pe Windows 10: instaleaza dependentele (pe Win11 sunt deja prezente)
if (-not $isWin11) {
    Write-Host "  [1/3] Microsoft VCLibs..." -ForegroundColor Yellow
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

    $step = "[3/3]"
} else {
    $step = "[1/1]"
}

# Descarca si instaleaza winget
Write-Host "  $step winget App Installer (~15 MB)..." -ForegroundColor Yellow
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

# Refresh PATH si verificare finala
$userPath    = [System.Environment]::GetEnvironmentVariable("PATH", "User")
$machinePath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
$env:PATH    = "$userPath;$machinePath"

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
    Write-Host "  [~] winget instalat - repornire CMD necesara." -ForegroundColor Yellow
    exit 2
}
