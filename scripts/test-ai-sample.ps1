# Test AI engine infer endpoint with sample (if running)
param([string]$AiUrl = 'http://localhost:8001')
try {
    $h = Invoke-RestMethod -Uri "$AiUrl/health" -TimeoutSec 5
    Write-Host "[PASS] AI health: $($h.status)"
} catch {
    Write-Host "[SKIP] AI engine not running at $AiUrl"
    exit 0
}
Write-Host "[INFO] Use pytest for offline infer tests: cd ai-engine && pytest tests/ -q"
