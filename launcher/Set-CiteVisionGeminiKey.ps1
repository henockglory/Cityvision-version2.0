#Requires -Version 5.1
<#
.SYNOPSIS
  Upsert GEMINI_API_KEY into WSL runtime ~/citevision-v2/.env + keyfile.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File launcher\Set-CiteVisionGeminiKey.ps1 -ApiKey 'saisissez votre nouvelle clé API'
.NOTES
  Replace the placeholder with a real Google AI Studio key, then re-run Start-CiteVision.ps1.
#>
param(
  [Parameter(Mandatory = $true)]
  [string]$ApiKey
)

$ErrorActionPreference = "Stop"
$Distro = "Ubuntu-24.04"
. (Join-Path $PSScriptRoot '..\installer\windows\Resolve-CiteVisionWslRoot.ps1')

if ([string]::IsNullOrWhiteSpace($ApiKey) -or $ApiKey -eq 'saisissez votre nouvelle clé API') {
  Write-Host "[FAIL] Remplacez le placeholder 'saisissez votre nouvelle clé API' par votre vraie cle." -ForegroundColor Red
  Write-Host "Exemple:" -ForegroundColor Yellow
  Write-Host "  powershell -ExecutionPolicy Bypass -File launcher\Set-CiteVisionGeminiKey.ps1 -ApiKey 'saisissez votre nouvelle clé API'" -ForegroundColor Cyan
  exit 2
}

try {
  $WslRoot = Resolve-CiteVisionWslRoot
} catch {
  Write-Host ("[FAIL] {0}" -f $_.Exception.Message) -ForegroundColor Red
  exit 1
}

# Escape for bash single-quoted string; never Write-Host the key.
$escaped = $ApiKey.Replace("'", "'\''")
$cmd = ("cd '{0}'; bash scripts/lib/set-gemini-key.sh '{1}'" -f $WslRoot, $escaped)
wsl -d $Distro -- bash -lc $cmd
$rc = $LASTEXITCODE
if ($rc -ne 0) {
  Write-Host ("[FAIL] set-gemini-key exit={0}" -f $rc) -ForegroundColor Red
  exit $rc
}

Write-Host ""
Write-Host "[OK] Cle Gemini mise a jour. Relancez:" -ForegroundColor Green
Write-Host "  powershell -ExecutionPolicy Bypass -File launcher\Start-CiteVision.ps1" -ForegroundColor Cyan
exit 0
