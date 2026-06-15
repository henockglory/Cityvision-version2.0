# Bench API health endpoint
param([string]$Url = 'http://localhost:8081/health', [int]$N = 50)
$times = @()
1..$N | ForEach-Object {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        Invoke-RestMethod -Uri $Url -TimeoutSec 5 | Out-Null
        $sw.Stop()
        $times += $sw.ElapsedMilliseconds
    } catch {
        $sw.Stop()
        $times += 9999
    }
}
$sorted = $times | Sort-Object
$p50 = $sorted[[int]($N * 0.5)]
$p95 = $sorted[[int]($N * 0.95)]
$avg = [math]::Round(($times | Measure-Object -Average).Average, 2)
Write-Host "API bench $Url N=$N avg=${avg}ms p50=${p50}ms p95=${p95}ms"
