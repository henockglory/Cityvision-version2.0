#Requires -Version 5.1
<#
  Teste si le compte peut ouvrir une session SERVICE (sans enregistrer le service).
  Usage: powershell -File test-service-logon.ps1
#>
param([string]$Root = "")

if (-not $Root) {
    $Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

$accountFile = Join-Path $Root "installer\.service_account"
$account = "$env:USERDOMAIN\$env:USERNAME"
if (Test-Path $accountFile) {
    $account = (Get-Content $accountFile -Raw).Trim()
}

Add-Type @'
using System;
using System.Runtime.InteropServices;
public class CvLogonTest {
    [DllImport("advapi32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
    public static extern bool LogonUser(string user, string domain, string password, int logonType, int logonProvider, out IntPtr token);
    [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
    public const int LOGON32_LOGON_SERVICE = 5;
    public const int LOGON32_PROVIDER_DEFAULT = 0;
}
'@

Write-Host "Compte: $account"
Write-Host ""
Write-Host "Saisissez le MOT DE PASSE Windows (pas le PIN) pour tester la connexion service..."
$cred = Get-Credential -UserName (($account -split '\\')[-1]) -Message "Test logon service pour $account"
if (-not $cred) { exit 2 }

$dom = $env:COMPUTERNAME
$user = $cred.UserName
if ($account -match '\\') {
    $p = $account -split '\\', 2
    $dom = if ($p[0] -eq '.') { $env:COMPUTERNAME } else { $p[0] }
    $user = $p[1]
}
$pass = $cred.GetNetworkCredential().Password
$token = [IntPtr]::Zero
$ok = [CvLogonTest]::LogonUser($user, $dom, $pass, 5, 0, [ref]$token)
if ($token -ne [IntPtr]::Zero) { [CvLogonTest]::CloseHandle($token) | Out-Null }

if ($ok) {
    Write-Host "[OK] Mot de passe accepte pour le service Windows." -ForegroundColor Green
    exit 0
}
$err = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
Write-Host "[ECHEC] Win32=$err - PIN ou mot de passe incorrect pour un service." -ForegroundColor Red
Write-Host "Configurez un mot de passe Windows (Parametres - Options de connexion), puis reessayez depuis l installateur."
exit 1
