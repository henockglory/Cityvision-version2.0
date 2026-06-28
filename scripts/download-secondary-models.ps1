# Download + verify secondary AI models (driver phone, seatbelt) from
# shared/ai-models.json on Windows. Verifies sha256 when pinned; honest
# degradation when a model is missing (the AI engine emits nothing, never fakes).
#
# Usage: powershell -File scripts/download-secondary-models.ps1 [-Fix]
param([switch]$Fix)
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
$Registry = Join-Path $Root 'shared\ai-models.json'
$Dest = Join-Path $Root 'ai-engine\models\secondary'

if (-not (Test-Path $Registry)) { Write-Host "[ERR] Registry not found: $Registry"; exit 1 }
if (-not (Test-Path $Dest)) { New-Item -ItemType Directory -Path $Dest | Out-Null }

$models = (Get-Content $Registry -Raw | ConvertFrom-Json).models
$ok = 0; $fail = 0

foreach ($m in $models) {
  $file = $m.file
  if ([string]::IsNullOrEmpty($file)) { continue }
  $out = Join-Path $Dest $file
  $sha = $m.sha256

  function Get-Sha($path) { (Get-FileHash -Algorithm SHA256 $path).Hash.ToLower() }

  if ((Test-Path $out) -and (-not $Fix)) {
    if (-not [string]::IsNullOrEmpty($sha)) {
      if ((Get-Sha $out) -eq $sha.ToLower()) { Write-Host "[OK] $($m.id) present + sha256 verified"; $ok++; continue }
      else { Write-Host "[WARN] $($m.id) sha256 mismatch - re-downloading" }
    } else { Write-Host "[OK] $($m.id) present (sha256 unpinned)"; $ok++; continue }
  }

  if ([string]::IsNullOrEmpty($m.url)) {
    Write-Host "[SKIP] $($m.id) has no URL - place $file manually in $Dest"; $fail++; continue
  }

  Write-Host "==> Downloading $($m.id) from $($m.url)"
  try {
    Invoke-WebRequest -Uri $m.url -OutFile "$out.tmp" -UseBasicParsing -ErrorAction Stop
    Move-Item -Force "$out.tmp" $out
    $got = Get-Sha $out
    if ((-not [string]::IsNullOrEmpty($sha)) -and ($got -ne $sha.ToLower())) {
      Write-Host "[ERR] $($m.id) sha256 mismatch (have $got, want $sha) - removing"
      Remove-Item -Force $out; $fail++; continue
    }
    if ([string]::IsNullOrEmpty($sha)) {
      Write-Host "[WARN] $($m.id) downloaded but sha256 UNPINNED. Freeze it: set sha256=$got in shared/ai-models.json"
    }
    Write-Host "[OK] $($m.id) ready ($got)"; $ok++
  } catch {
    if (Test-Path "$out.tmp") { Remove-Item -Force "$out.tmp" }
    Write-Host "[ERR] $($m.id) download failed - behavior degrades honestly (emits nothing)"; $fail++
  }
}

Write-Host "==> Secondary models: $ok ok, $fail missing/failed"
exit 0
