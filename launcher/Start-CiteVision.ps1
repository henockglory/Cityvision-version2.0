#Requires -Version 5.1
<#
.SYNOPSIS
  Start the CiteVision product stack.
.NOTES
  powershell -ExecutionPolicy Bypass -File launcher\Start-CiteVision.ps1
  Exit 0 when services, health gate, and Gemini probe pass.
  ASCII-only body for Windows PowerShell 5.1.
#>
$ErrorActionPreference = "Continue"
$Distro = "Ubuntu-24.04"
. (Join-Path $PSScriptRoot '..\installer\windows\Resolve-CiteVisionWslRoot.ps1')

function ConvertTo-WslPath {
  param([Parameter(Mandatory = $true)][string]$WinPath)
  $full = [System.IO.Path]::GetFullPath($WinPath)
  if ($full -match '^([A-Za-z]):\\?(.*)$') {
    $drive = $Matches[1].ToLowerInvariant()
    $rest = ($Matches[2] -replace '\\', '/')
    return ("/mnt/{0}/{1}" -f $drive, $rest).TrimEnd('/')
  }
  return ($full -replace '\\', '/')
}

function Write-CiteStartLine {
  param([AllowNull()][string]$Line)
  if ($null -eq $Line) { return }
  $t = ("{0}" -f $Line).TrimEnd()
  if ($t.Length -eq 0) { return }

  # Hide lab / mirror / path noise from customer-facing console.
  if ($t -match 'live-preview|Sync critical paths|mirror ->|/mnt/c/Users/|skip missing|ALL_SYNC_OK|WSL_OK') {
    return
  }

  $d = $t
  $d = $d -replace '/home/[^/\s]+/citevision[^/\s]*', 'runtime'
  $d = $d -replace 'ROOT=/[^\s]+', 'ROOT=runtime'
  $d = $d -replace 'CITEVISION_ROOT=/[^\s]+', 'CITEVISION_ROOT=runtime'

  if ($d -match '^===\s*(.+?)\s*===') {
    Write-Host ("  > {0}" -f $Matches[1].Trim()) -ForegroundColor Cyan
    return
  }
  if ($d -match '^\[OK\]') {
    Write-Host ("  {0}" -f $d) -ForegroundColor Green
    return
  }
  if ($d -match '^\[FAIL\]') {
    Write-Host ("  {0}" -f $d) -ForegroundColor Red
    return
  }
  if ($d -match '^\[WARN\]') {
    Write-Host ("  {0}" -f $d) -ForegroundColor Yellow
    return
  }
  if ($d -match '^\[INFO\]') {
    Write-Host ("  {0}" -f $d) -ForegroundColor DarkGray
    return
  }
  Write-Host ("  {0}" -f $d)
}

try {
  $WslRoot = Resolve-CiteVisionWslRoot
} catch {
  Write-Host ("[FAIL] {0}" -f $_.Exception.Message) -ForegroundColor Red
  exit 1
}

$ProductRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$WslProductRoot = ConvertTo-WslPath $ProductRoot

Write-Host ""
Write-Host "CiteVision" -ForegroundColor Cyan
Write-Host "Starting services..." -ForegroundColor Cyan
Write-Host ""

$prev = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
wsl -d $Distro -e true 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
  $ErrorActionPreference = $prev
  Write-Host "[FAIL] Runtime environment is not available." -ForegroundColor Red
  exit 1
}
$ErrorActionPreference = $prev

$probe = ('test -f "{0}/scripts/lib/start-full-stack.sh"' -f $WslRoot)
wsl -d $Distro -- bash -lc $probe
if ($LASTEXITCODE -ne 0) {
  Write-Host "[FAIL] CiteVision runtime is incomplete. Reinstall or repair the product." -ForegroundColor Red
  exit 1
}

# Optional silent refresh from this product tree (no path printed).
$syncPreview = ('SRC="{0}"; DST="{1}"; SCRIPT="$SRC/scripts/lib/sync-live-preview-ui.sh"; if [ -f "$SCRIPT" ]; then bash "$SCRIPT" "$SRC" "$DST" >/dev/null 2>&1 || true; fi' -f $WslProductRoot, $WslRoot)
wsl -d $Distro -- bash -lc $syncPreview | Out-Null

# Stream start output line-by-line (stdbuf avoids "all at once" block buffering).
$bashCmd = ("cd '{0}'; export STRICT_INSTALL_HEALTH=1; export PYTHONUNBUFFERED=1; if command -v stdbuf >/dev/null 2>&1; then stdbuf -oL -eL bash scripts/lib/start-full-stack.sh; else bash scripts/lib/start-full-stack.sh; fi" -f $WslRoot)

$logLines = New-Object System.Collections.Generic.List[string]
& wsl.exe -d $Distro -- bash -lc $bashCmd 2>&1 | ForEach-Object {
  $line = "$_"
  [void]$logLines.Add($line)
  Write-CiteStartLine $line
}
$rc = $LASTEXITCODE
$joined = [string]::Join("`n", $logLines)

if ($rc -ne 0) {
  Write-Host ""
  Write-Host "[FAIL] CiteVision could not start completely." -ForegroundColor Red
  if ($joined -match 'GEMINI_PROBE_FAILED|gemini_probe FAILED|gemini_configured missing|GEMINI_PROBE') {
    Write-Host ""
    Write-Host "[FAIL] Vision AI key missing or unreachable." -ForegroundColor Red
    Write-Host "Set your API key, then start again:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  powershell -ExecutionPolicy Bypass -File launcher\Set-CiteVisionGeminiKey.ps1 -ApiKey 'YOUR_API_KEY'" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  powershell -ExecutionPolicy Bypass -File launcher\Start-CiteVision.ps1" -ForegroundColor Cyan
    Write-Host ""
  }
  exit $rc
}

Write-Host ""
Write-Host "[OK] CiteVision is ready" -ForegroundColor Green
Write-Host "     Open http://127.0.0.1:5174" -ForegroundColor Green
Write-Host ""
exit 0
