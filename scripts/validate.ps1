# Citevision v2 validation (Windows)
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Fail = 0

function Check($Name, $Path) {
    if (Test-Path $Path) { Write-Host "[PASS] $Name" } else { Write-Host "[FAIL] $Name"; $script:Fail++ }
}

Write-Host "=== Citevision v2 Validation ==="
Check "CLARIFICATIONS" "docs/CLARIFICATIONS.md"
Check "backend" "backend/go.mod"
Check "frontend" "frontend/package.json"
Check "rules-engine" "rules-engine/go.mod"
Check "ai-engine" "ai-engine/pyproject.toml"
Check "no mock.ts" "frontend/src/components/EmptyState.tsx"
if (Test-Path "frontend/src/data/mock.ts") { Write-Host "[FAIL] mock.ts exists"; $Fail++ } else { Write-Host "[PASS] no mock.ts" }

if (Select-String -Path "frontend/src" -Pattern "demoLogin|withMockFallback" -Quiet) {
    Write-Host "[FAIL] mock patterns found in frontend"
    $Fail++
} else {
    Write-Host "[PASS] zero mock patterns"
}

Push-Location backend; go test ./...; if ($LASTEXITCODE -ne 0) { $Fail++ }; Pop-Location
Push-Location rules-engine; go test ./...; if ($LASTEXITCODE -ne 0) { $Fail++ }; Pop-Location
Push-Location ai-engine; python -m pytest tests/ -q; if ($LASTEXITCODE -ne 0) { $Fail++ }; Pop-Location
Push-Location frontend; npm run build --silent; if ($LASTEXITCODE -ne 0) { $Fail++ }; Pop-Location

Write-Host "FAIL=$Fail"
if ($Fail -gt 0) { exit 1 }
