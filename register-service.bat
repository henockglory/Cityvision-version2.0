@echo off
setlocal EnableDelayedExpansion
:: Register citevision Windows service (auto-elevate via UAC + Windows password prompt)
:: This is the ONLY supported way to register the Windows service.
:: Usage: register-service.bat              (interactive, pause at end)
::        register-service.bat -Handover     (installateur : bascule vers le service)
::        register-service.bat -Silent       (sans pause)

set "SILENT=0"
set "HANDOVER=0"
for %%A in (%*) do (
    if /i "%%A"=="-Silent" set "SILENT=1"
    if /i "%%A"=="-Handover" set "HANDOVER=1"
)

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

:: Compte interactif (avant UAC — requis pour WSL, pas LocalSystem)
if not exist "%ROOT%\installer" mkdir "%ROOT%\installer"
set "SVC_ACCT=%USERDOMAIN%\%USERNAME%"
> "%ROOT%\installer\.service_account" echo !SVC_ACCT!

:: Read start mode from installer/.service_start_mode if present
set "MODE=auto"
if exist "%ROOT%\installer\.service_start_mode" (
    set /p MODE=<"%ROOT%\installer\.service_start_mode"
)

if not "!SILENT!"=="1" (
    echo ============================================================
    echo   CitéVision - Enregistrement du service Windows
    echo   Mode: !MODE!
    echo ============================================================
    echo.
    echo   1. Acceptez la fenetre UAC ^(administrateur^)
    echo   2. Saisissez votre mot de passe Windows quand demande
    echo      ^(obligatoire : WSL ne fonctionne pas sous LocalSystem^)
    echo.
)

:: Auto-elevate if not admin
net session >nul 2>&1
if !errorlevel! neq 0 (
    if not "!SILENT!"=="1" echo [INFO] Elevation administrateur requise - fenetre UAC...
    set "ELEV_ARGS="
    if "!SILENT!"=="1" set "ELEV_ARGS=-Silent"
    if "!HANDOVER!"=="1" set "ELEV_ARGS=!ELEV_ARGS! -Handover"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -ArgumentList '!ELEV_ARGS!' -Verb RunAs -Wait"
    exit /b !errorlevel!
)

set "PS_ARGS=-StartMode !MODE! -Elevated"
if "!HANDOVER!"=="1" set "PS_ARGS=!PS_ARGS! -Handover"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\installer\windows\install-service.ps1" !PS_ARGS!
set "RC=!errorlevel!"

if not "!SILENT!"=="1" (
    echo.
    if !RC! equ 0 (
        echo [OK] Service citevision enregistre.
        echo      Nom affiche : CiteVision - AI Video Surveillance
        echo      Verifiez dans services.msc
    ) else (
        echo [ERR] Enregistrement echoue - code !RC!
        echo       Consultez les messages ci-dessus.
    )
    echo.
    pause
)
exit /b !RC!
