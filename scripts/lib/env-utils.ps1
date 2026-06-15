function Load-DotEnv {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return }
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq '' -or $line.StartsWith('#')) { return }
        $idx = $line.IndexOf('=')
        if ($idx -lt 1) { return }
        $key = $line.Substring(0, $idx).Trim()
        $val = $line.Substring($idx + 1).Trim()
        if ($val.StartsWith('"') -and $val.EndsWith('"')) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($key, $val, 'Process')
    }
}

function New-RandomHex {
    param([int]$Bytes = 16)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $buf = New-Object byte[] $Bytes
    $rng.GetBytes($buf)
    ($buf | ForEach-Object { '{0:x2}' -f $_ }) -join ''
}

function Ensure-EnvFile {
    param([string]$Root)
    $envPath = Join-Path $Root '.env'
    $examplePath = Join-Path $Root '.env.example'
    if (Test-Path $envPath) { return $envPath }
    if (-not (Test-Path $examplePath)) {
        throw ".env.example not found at $examplePath"
    }
    Copy-Item $examplePath $envPath
    $jwt = New-RandomHex 24
    $audit = New-RandomHex 24
    $camKey = New-RandomHex 32
    $content = Get-Content $envPath -Raw
    $content = $content -replace 'JWT_SECRET=.*', "JWT_SECRET=$jwt"
    $content = $content -replace 'AUDIT_SIGNING_KEY=.*', "AUDIT_SIGNING_KEY=$audit"
    $content = $content -replace 'CAMERA_CREDENTIAL_KEY=.*', "CAMERA_CREDENTIAL_KEY=$camKey"
    Set-Content -Path $envPath -Value $content -NoNewline
    Write-Host "[INFO] Created .env from .env.example with generated secrets"
    return $envPath
}

function Test-PortFree {
    param([int]$Port)
    $inUse = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    return -not $inUse
}

function Wait-HttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSec = 60,
        [int]$IntervalMs = 2000
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) { return $true }
        } catch { }
        Start-Sleep -Milliseconds $IntervalMs
    }
    return $false
}

function Start-BackgroundProcess {
    param(
        [string]$Name,
        [string]$WorkingDirectory,
        [string]$Command,
        [string]$LogDir
    )
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
    $logFile = Join-Path $LogDir "$Name.log"
    $pidFile = Join-Path $LogDir "$Name.pid"
    $proc = Start-Process -FilePath 'powershell' -ArgumentList @(
        '-NoProfile', '-Command',
        "Set-Location '$WorkingDirectory'; $Command 2>&1 | Tee-Object -FilePath '$logFile'"
    ) -PassThru -WindowStyle Hidden
    Set-Content -Path $pidFile -Value $proc.Id
    Write-Host "[OK] Started $Name (PID $($proc.Id)) -> $logFile"
    return $proc.Id
}

function Stop-ProcessFromPidFile {
    param([string]$PidFile)
    if (-not (Test-Path $PidFile)) { return }
    $pid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($pid -and (Get-Process -Id $pid -ErrorAction SilentlyContinue)) {
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        Write-Host "[OK] Stopped PID $pid"
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}
