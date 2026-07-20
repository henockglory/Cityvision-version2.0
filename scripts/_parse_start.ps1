$errs = $null
$path = 'C:\Users\gheno\citevision\launcher\Start-CiteVision.ps1'
[void][System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$null, [ref]$errs)
if ($errs -and $errs.Count -gt 0) {
  $errs | ForEach-Object { Write-Host $_.Message }
  exit 1
}
Write-Host 'PARSE_OK'
exit 0
