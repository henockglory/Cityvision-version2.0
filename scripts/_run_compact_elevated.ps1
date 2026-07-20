$ErrorActionPreference = "Continue"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$wrapLog = "C:\Users\gheno\citevision\scripts\compact-elevated-$stamp.log"
function W($m) { $line = "$(Get-Date -Format o) $m"; Add-Content $wrapLog $line; Write-Host $line }

W "elevated wrapper start, admin=$(([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))"
try {
  & "C:\Users\gheno\citevision\scripts\compact-wsl-vhdx.ps1"
  W "compact script finished"
} catch {
  W "EXCEPTION: $_"
  exit 1
}
W "WRAPPER_DONE"
exit 0
