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

# Detectie Windows 11 via registry (sigura in PS 5.1)
$buildNum = 0
try {
    $buildNum = [int](Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion").CurrentBuildNumber
} catch {}
$isWin11 = ($buildNum -ge 22000)

Write-Host ""
Write-Host "  Instalez winget (build OS: $buildNum)..." -ForegroundColor Yellow
Write-Host ""

# Temp dir robust - GetTempPath() nu depinde de env:TEMP
$tempBase = [System.IO.Path]::GetTempPath()
if (-not $tempBase -or -not (Test-Path $tempBase)) { $tempBase = "C:\Windows\Temp" }
$tempDir = Join-Path $tempBase "winget_tradingbot"
New-Item -ItemType Directory -Force -Path $tempDir -ErrorAction SilentlyContinue | Out-Null

if (-not (Test-Path $tempDir)) {
    Write-Host "  [!] Nu pot crea directorul temporar: $tempDir" -ForegroundColor Red
    exit 1
}

# --------------------------------------------------------------------------
# PASUL 1: Dependente de baza (doar pe Win10 - pe Win11 sunt preinstalate)
# --------------------------------------------------------------------------
if (-not $isWin11) {
    Write-Host "  [1/4] Microsoft VCLibs..." -ForegroundColor Yellow
    try {
        $vcFile = Join-Path $tempDir "VCLibs.appx"
        Invoke-WebRequest "https://aka.ms/Microsoft.VCLibs.x64.14.00.Desktop.appx" `
            -OutFile $vcFile -UseBasicParsing -TimeoutSec 60
        Add-AppxPackage $vcFile -ErrorAction SilentlyContinue
        Write-Host "        OK" -ForegroundColor Green
    } catch {
        Write-Host "        WARN: $($_.Exception.Message)" -ForegroundColor DarkYellow
    }

    Write-Host "  [2/4] Microsoft UI.Xaml 2.8..." -ForegroundColor Yellow
    try {
        $xamlFile = Join-Path $tempDir "UIXaml.appx"
        Invoke-WebRequest "https://github.com/microsoft/microsoft-ui-xaml/releases/download/v2.8.6/Microsoft.UI.Xaml.2.8.x64.appx" `
            -OutFile $xamlFile -UseBasicParsing -TimeoutSec 60
        Add-AppxPackage $xamlFile -ErrorAction SilentlyContinue
        Write-Host "        OK" -ForegroundColor Green
    } catch {
        Write-Host "        WARN: $($_.Exception.Message)" -ForegroundColor DarkYellow
    }
    $rtStep  = "[3/4]"
    $wgStep  = "[4/4]"
} else {
    $rtStep  = "[1/2]"
    $wgStep  = "[2/2]"
}

# --------------------------------------------------------------------------
# PASUL 2: Windows App Runtime 1.8 (cerut de winget 1.26+)
# --------------------------------------------------------------------------
Write-Host "  $rtStep Windows App Runtime 1.8..." -ForegroundColor Yellow
$rtInstalled = $false
try {
    $rt = Get-AppxPackage -Name "Microsoft.WindowsAppRuntime.1.8" -ErrorAction SilentlyContinue
    if ($rt) {
        Write-Host "        deja instalat ($($rt.Version))" -ForegroundColor Green
        $rtInstalled = $true
    }
} catch {}

if (-not $rtInstalled) {
    try {
        $rtFile = Join-Path $tempDir "WinAppRuntime.exe"
        Invoke-WebRequest "https://aka.ms/windowsappsdk/1.8/latest/windowsappruntimeinstall-x64.exe" `
            -OutFile $rtFile -UseBasicParsing -TimeoutSec 90
        $proc = Start-Process $rtFile -ArgumentList "--quiet --norestart" -Wait -PassThru
        if ($proc.ExitCode -eq 0 -or $proc.ExitCode -eq 3010) {
            Write-Host "        OK" -ForegroundColor Green
        } else {
            Write-Host "        WARN: exit code $($proc.ExitCode)" -ForegroundColor DarkYellow
        }
    } catch {
        Write-Host "        WARN: $($_.Exception.Message)" -ForegroundColor DarkYellow
    }
}

# --------------------------------------------------------------------------
# PASUL 3: winget (App Installer)
# --------------------------------------------------------------------------
Write-Host "  $wgStep winget App Installer (~15 MB)..." -ForegroundColor Yellow
$wingetOk = $false
try {
    $wingetFile = Join-Path $tempDir "winget.msixbundle"
    Invoke-WebRequest "https://github.com/microsoft/winget-cli/releases/latest/download/Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle" `
        -OutFile $wingetFile -UseBasicParsing -TimeoutSec 120
    # -ErrorAction Stop face ca erorile non-terminatoare sa fie prinse de catch
    Add-AppxPackage $wingetFile -ForceApplicationShutdown -ErrorAction Stop
    Write-Host "        OK" -ForegroundColor Green
    $wingetOk = $true
} catch {
    Write-Host "        [!] $($_.Exception.Message)" -ForegroundColor Red
}

Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue

if (-not $wingetOk) {
    Write-Host ""
    Write-Host "  [!] Instalare winget esuata." -ForegroundColor Red
    exit 1
}

# Refresh PATH si verificare finala
$userPath    = [System.Environment]::GetEnvironmentVariable("PATH", "User")
$machinePath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
$env:PATH    = "$userPath;$machinePath"

$wingetExe = Get-Item "$env:LOCALAPPDATA\Microsoft\WindowsApps\winget.exe" -ErrorAction SilentlyContinue
if ($wingetExe) { $env:PATH = "$($wingetExe.DirectoryName);$env:PATH" }

if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host ""
    Write-Host "  [+] winget instalat si activ!" -ForegroundColor Green
    exit 0
} else {
    Write-Host ""
    Write-Host "  [~] winget instalat - repornire CMD necesara." -ForegroundColor Yellow
    exit 2
}
