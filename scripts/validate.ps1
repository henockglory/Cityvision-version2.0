# Citévision 2.0 - Windows validation
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Pass = 0
$Fail = 0

function Test-Check($Name, $Path) {
    if (Test-Path $Path) {
        Write-Host "[PASS] $Name"
        $script:Pass++
    } else {
        Write-Host "[FAIL] $Name"
        $script:Fail++
    }
}

Write-Host "=== Citevision 2.0 Validation ==="

Test-Check "README" "README.md"
Test-Check "PROMPT-AGENT" "docs/PROMPT-AGENT.md"
Test-Check "docker-compose" "docker-compose.yml"
Test-Check "backend" "backend/go.mod"
Test-Check "frontend" "frontend/package.json"
Test-Check "ai-engine" "ai-engine/pyproject.toml"

Write-Host ""
Write-Host "Go tests..."
Push-Location backend
go test ./...
if ($LASTEXITCODE -eq 0) { $Pass++; Write-Host "[PASS] go test" } else { $Fail++ }
Pop-Location

Write-Host "Python tests..."
Push-Location ai-engine
python -m pytest tests/ -q
if ($LASTEXITCODE -eq 0) { $Pass++; Write-Host "[PASS] pytest" } else { $Fail++ }
Pop-Location

Write-Host "Frontend build..."
Push-Location frontend
npm run build --silent
if ($LASTEXITCODE -eq 0) { $Pass++; Write-Host "[PASS] npm build" } else { $Fail++ }
Pop-Location

Write-Host ""
Write-Host "Summary PASS=$Pass FAIL=$Fail"
if ($Fail -gt 0) { exit 1 }
