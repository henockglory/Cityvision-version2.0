#Requires -Version 5.1
<#
.SYNOPSIS
  Mirror citevision_optimized -> git repos and/or C:\Citevision.

.DESCRIPTION
  Source of truth: citevision_optimized (no .git).
  Copies all project dirs + root files. Preserves .git in targets.
  Skips heavy/generated: node_modules, .venv, logs, __pycache__, .cursor.
  Does NOT overwrite target .env or generated.env (machine-local).

.EXAMPLE
  powershell -File scripts/sync-from-optimized.ps1
  powershell -File scripts/sync-from-optimized.ps1 -Targets citevision-v2,Citevision
#>
param(
    [string[]]$Targets = @(
        'c:\Users\gheno\citevision-v2',
        'c:\Users\gheno\citevision',
        'C:\Citevision'
    )
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Src = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

$Dirs = @(
    '.github',
    'ai-engine',
    'backend',
    'data',
    'docs',
    'frontend',
    'infra',
    'installer',
    'rules-engine',
    'scripts',
    'shared',
    'tests',
    'vendor',
    'video-engine',
    'web'
)

$RootFiles = @(
    '.env.example',
    '.gitattributes',
    '.gitignore',
    'AGENT_CHECKPOINT.md',
    'Makefile',
    'OPTIMIZATION-REPORT.md',
    'README.md',
    'WORKSPACE.md',
    'register-service.bat',
    'add-windows-password.bat',
    'setup.bat',
    'setup.sh',
    'sync-to-citevision.bat'
)

$RoboFlags = @(
    '/E', '/R:0', '/W:0', '/NFL', '/NJH', '/NJS',
    '/XD', 'node_modules', '.venv', '__pycache__', 'logs', '.git', '.cursor',
    '/XF', '*.pyc',
    '/XJ'
)

function Sync-Tree {
    param([string]$Destination)
    if (-not (Test-Path $Destination)) {
        New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    }
    Write-Host "[SYNC] $Src -> $Destination"
    foreach ($dir in $Dirs) {
        $from = Join-Path $Src $dir
        if (-not (Test-Path $from)) { continue }
        $to = Join-Path $Destination $dir
        & robocopy $from $to @RoboFlags | Out-Null
    }
    foreach ($file in $RootFiles) {
        $from = Join-Path $Src $file
        if (Test-Path $from) {
            Copy-Item -Path $from -Destination (Join-Path $Destination $file) -Force
        }
    }
    # docker-compose at root if present
    Get-ChildItem -Path $Src -Filter 'docker-compose*.yml' -File -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item $_.FullName (Join-Path $Destination $_.Name) -Force
    }
}

Write-Host "=== CitéVision sync-from-optimized ==="
Write-Host "Source: $Src"
Write-Host ""

foreach ($target in $Targets) {
    Sync-Tree -Destination $target
}

Write-Host ""
Write-Host "[OK] Sync complete."
