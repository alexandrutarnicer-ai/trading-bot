# Opreste procesele care asculta pe porturile date. Apelat din start_ui.bat.
# ATENTIE: invocat cu `powershell -File ... -Ports 8000,5173` — cu -File argumentele
# sosesc ca STRING (nu array!), asa ca acceptam string si il despartim manual.
# (Cu param([int[]]) vechiul apel producea "80005173" -> overflow UInt16 -> scriptul
# nu omora NIMIC, silentios. Bug istoric, reparat 2026-07-13.)
param([string]$Ports = "8000,5173")

foreach ($portStr in ($Ports -split "[ ,]+" | Where-Object { $_ })) {
    $port = 0
    if (-not [int]::TryParse($portStr, [ref]$port)) { continue }
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        $procId = $c.OwningProcess
        try {
            $name = (Get-Process -Id $procId -ErrorAction Stop).ProcessName
            # taskkill /T = omoara si COPIII procesului. Un copil multiprocessing
            # mosteneste handle-ul socketului si tine portul ocupat chiar si dupa
            # moartea parintelui (vazut live 2026-07-13 pe uvicorn/api).
            taskkill /F /T /PID $procId 2>$null | Out-Null
            Write-Host "  [kill_ports] oprit PID $procId ($name, cu copii) de pe portul $port"
        } catch {
            Write-Host "  [kill_ports] nu am putut opri PID $procId de pe portul ${port}: $_"
        }
    }
}
