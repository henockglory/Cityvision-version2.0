param([string]$Root = 'C:\Users\gheno\citevision-v2')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'SilentlyContinue'
if (-not $Root) { $Root = 'C:\Users\gheno\citevision-v2' }

$modeFile = Join-Path $Root 'installer\.service_start_mode'
if (Test-Path $modeFile) {
    $mode = (Get-Content -Path $modeFile -Raw -Encoding UTF8).Trim().ToLower()
    if ($mode -eq 'manual') { exit 0 }
}

function Test-UrlHealthy([string]$Uri) {
    try {
        $r = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 4
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500)
    } catch { return $false }
}

function Test-WinApiHealthy {
    if (Test-UrlHealthy 'http://127.0.0.1:8081/health') { return $true }
    if (Test-UrlHealthy 'http://[::1]:8081/health') { return $true }
    return $false
}

function Test-WslApiHealthy {
    & wsl.exe -- bash -lc "curl -sf --max-time 3 http://127.0.0.1:8081/health >/dev/null 2>&1" | Out-Null
    return ($LASTEXITCODE -eq 0)
}

$winOk = Test-WinApiHealthy
if (-not $winOk) {
    $wslOk = Test-WslApiHealthy
    if ($wslOk) {
        # Relay gap: API alive in WSL — do not start-linux (destroys in-flight jobs).
        & wsl.exe -- bash -lc "curl -sf --max-time 2 http://127.0.0.1:8081/health >/dev/null 2>&1 || true" | Out-Null
    } else {
        . (Join-Path $Root 'installer\windows\Resolve-CiteVisionWslRoot.ps1')
        try {
            $useRoot = Resolve-CiteVisionWslRoot
        } catch {
            exit 1
        }
        if ($useRoot -match '^/mnt/') { exit 1 }
        $bashCmd = ("cd '{0}'; bash scripts/start-linux.sh" -f $useRoot)
        & wsl.exe -- bash -lc $bashCmd
    }
}

$loopScript = Join-Path $Root 'installer\windows\citevision-watchdog-loop.ps1'
$loopLock = Join-Path $Root 'logs\.watchdog-loop.pid'
$startLoop = $true
if (Test-Path $loopLock) {
    try {
        $pidVal = [int](Get-Content -Path $loopLock -Raw).Trim()
        if (Get-Process -Id $pidVal -ErrorAction SilentlyContinue) { $startLoop = $false }
    } catch {}
}
if ($startLoop -and (Test-Path $loopScript)) {
    $psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    Start-Process -FilePath $psExe -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
        '-File', $loopScript, '-Root', $Root
    ) -WindowStyle Hidden | Out-Null
}
exit 0
