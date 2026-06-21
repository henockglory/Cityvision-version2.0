@echo off
setlocal EnableDelayedExpansion
:: Register citevision Windows service (auto-elevate via UAC + Windows password prompt)
:: This is the ONLY supported way to register the Windows service.
:: Usage: register-service.bat          (interactive, pause at end)
::        register-service.bat -Silent (installer — no pause)

set "SILENT=0"
if /i "%~1"=="-Silent" set "SILENT=1"

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

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
    if "!SILENT!"=="1" (
        powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -ArgumentList '-Silent' -Verb RunAs -Wait"
    ) else (
        powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs -Wait"
    )
    exit /b !errorlevel!
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\installer\windows\install-service.ps1" -StartMode !MODE! -Elevated
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
