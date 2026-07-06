@echo off
setlocal EnableDelayedExpansion
:: Register citevision Windows service (auto-elevate via UAC + Windows password prompt)
:: This is the ONLY supported way to register the Windows service.
:: Usage: register-service.bat              (interactive, pause at end on error)
::        register-service.bat -Handover     (installer: handover stack to service)
::        register-service.bat -Silent       (no pause on error)

set "SILENT=0"
set "HANDOVER=0"
for %%A in (%*) do (
    if /i "%%A"=="-Silent" set "SILENT=1"
    if /i "%%A"=="-Handover" set "HANDOVER=1"
)

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

if not exist "%ROOT%\installer" mkdir "%ROOT%\installer"
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"

:: Compte interactif AVANT UAC (WSL requiert le compte utilisateur, pas LocalSystem)
echo %USERDOMAIN%\%USERNAME%> "%ROOT%\installer\.service_account"

set "MODE=auto"
if exist "%ROOT%\installer\.service_start_mode" (
    set /p MODE=<"%ROOT%\installer\.service_start_mode"
)

set "LOG=%ROOT%\logs\register-service.log"
set "RESULT=%TEMP%\citevision-svc-result.json"

if not "!SILENT!"=="1" (
    echo ============================================================
    echo   CiteVision - Enregistrement du service Windows
    echo   Mode: !MODE!
    echo ============================================================
    echo.
    echo   Une fenetre PowerShell va s ouvrir.
    echo   1. Acceptez UAC ^(administrateur^)
    echo   2. Saisissez votre MOT DE PASSE Windows ^(pas le PIN^)
    echo      Parametres - Comptes - Options de connexion - Mot de passe
    echo.
)

set "PS_ARGS=-Root "!ROOT!" -StartMode "!MODE!" -LogFile "!LOG!" -ResultFile "!RESULT!""
if "!SILENT!"=="1" set "PS_ARGS=!PS_ARGS! -Silent"
if "!HANDOVER!"=="1" set "PS_ARGS=!PS_ARGS! -Handover"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\installer\windows\register-elevated.ps1" !PS_ARGS!
set "RC=!errorlevel!"
exit /b !RC!
