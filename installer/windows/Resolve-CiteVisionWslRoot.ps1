#Requires -Version 5.1
<#
.SYNOPSIS
  Resolve native WSL runtime root for CiteVision (never /mnt/*).
.NOTES
  Dot-source friendly. Returns path string from Resolve-CiteVisionWslRoot.
  Honors CITEVISION_WSL_ROOT when set; else probes $HOME/citevision-v2 in WSL.
  ASCII-only.
#>
function Resolve-CiteVisionWslRoot {
    [CmdletBinding()]
    param()

    $root = $env:CITEVISION_WSL_ROOT
    if ([string]::IsNullOrWhiteSpace($root)) {
        $out = & wsl.exe -- bash -lc 'printf %s "$HOME/citevision-v2"' 2>$null
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($out)) {
            throw 'Failed to resolve WSL runtime root (wsl bash probe failed)'
        }
        $root = $out.Trim()
    }

    if ($root -match '^/mnt/') {
        throw ("Refuse WSL runtime root under /mnt/* (got: {0}). Use native ~/citevision-v2 or set CITEVISION_WSL_ROOT." -f $root)
    }

    $probe = ('test -f "{0}/scripts/start-linux.sh"' -f $root)
    & wsl.exe -- bash -lc $probe 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw ("WSL runtime incomplete: missing {0}/scripts/start-linux.sh - run scripts/sync-to-wsl.sh" -f $root)
    }

    return $root
}

if ($MyInvocation.InvocationName -ne '.') {
    try {
        Write-Output (Resolve-CiteVisionWslRoot)
        exit 0
    } catch {
        Write-Error $_.Exception.Message
        exit 1
    }
}
