# Find WSL VHDX sizes
$paths = @(
  "$env:LOCALAPPDATA\Packages",
  "$env:LOCALAPPDATA\wsl",
  "$env:LOCALAPPDATA\Docker\wsl"
)
Write-Host "=== VHDX files ==="
foreach ($root in $paths) {
  if (Test-Path $root) {
    Get-ChildItem -Path $root -Recurse -Filter '*.vhdx' -ErrorAction SilentlyContinue |
      ForEach-Object {
        $gb = [math]::Round($_.Length / 1GB, 2)
        Write-Host ("{0}  {1} GB  mtime={2}" -f $_.FullName, $gb, $_.LastWriteTime)
      }
  }
}
Write-Host "=== wsl -l -v ==="
wsl -l -v
Write-Host "=== sparse note ==="
Write-Host "wsl --manage <distro> --set-sparse true has no query API; check not run in this audit unless previously documented."
