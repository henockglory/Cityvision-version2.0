#Requires -Version 5.1
<#
  Guide utilisateur : ajouter un mot de passe Windows (obligatoire si connexion par PIN seul).
  Appele par add-windows-password.bat ou l installateur.
#>
param(
    [switch]$OpenSettings = $true,
    [switch]$Silent
)

try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$account = "$env:USERDOMAIN\$env:USERNAME"
$accountFile = Join-Path $Root "installer\.service_account"
if (Test-Path $accountFile) {
    $fromFile = (Get-Content $accountFile -Raw).Trim()
    if ($fromFile) { $account = $fromFile }
}

$text = @"
CiteVision a besoin d un MOT DE PASSE Windows (pas le PIN).

Windows ne permet pas aux services (services.msc) d utiliser le PIN Microsoft Hello.

Compte concerne : $account

=== Etapes (Windows 11) ===

1. Parametres s ouvre sur Options de connexion
2. Section "Methodes de connexion" ou "Compte Microsoft"
3. Cliquez "Ajouter" sous MOT DE PASSE
   (ou "Mot de passe" puis "Configurer")
4. Suivez l assistant (compte Microsoft en ligne si demande)

Vous gardez votre PIN pour vous connecter au quotidien.
Le mot de passe sert uniquement au service CitéVision en arriere-plan.

Ensuite : cliquez Reessayer dans l installateur CitéVision.

Aide en ligne :
https://account.microsoft.com/security
"@

if ($OpenSettings) {
    try { Start-Process "ms-settings:signinoptions" } catch {}
    Start-Sleep -Milliseconds 800
    try { Start-Process "https://account.microsoft.com/security" } catch {}
}

if ($Silent) {
    Write-Host $text
    exit 0
}

try {
    Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
    [void][System.Windows.Forms.MessageBox]::Show(
        $text,
        "CiteVision - Mot de passe Windows requis",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    )
} catch {
    Write-Host $text
    if (-not $Silent) { Read-Host "Appuyez sur Entree" }
}

exit 0
