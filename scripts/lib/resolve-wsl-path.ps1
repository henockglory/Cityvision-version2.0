function Get-WslProjectRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WindowsRoot
    )
    $resolved = (Resolve-Path -LiteralPath $WindowsRoot -ErrorAction SilentlyContinue).Path
    if (-not $resolved) { $resolved = $WindowsRoot }
    try {
        $wslPath = (wsl -- wslpath -a $resolved 2>$null)
        if ($LASTEXITCODE -eq 0 -and $wslPath) {
            return $wslPath.Trim()
        }
    } catch { }
    $drive = $resolved.Substring(0, 1).ToLower()
    $rest = $resolved.Substring(2).Replace('\', '/')
    return "/mnt/$drive$rest"
}
