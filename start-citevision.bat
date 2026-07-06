@echo off
setlocal EnableDelayedExpansion
:: Manual start — CitéVision stack via WSL (no Windows service required)
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

where wsl.exe >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] WSL introuvable. Installez WSL2 puis relancez setup.bat
    pause
    exit /b 1
)

echo ============================================================
echo   CitéVision - Demarrage manuel
echo ============================================================
echo.

for /f "usebackq delims=" %%P in (`wsl wslpath -a "%ROOT%" 2^>nul`) do set "WSL_ROOT=%%P"
if not defined WSL_ROOT set "WSL_ROOT=/mnt/c/Citevision"

wsl -- bash -lc "cd '%WSL_ROOT%' && bash scripts/start-linux.sh"
set "RC=!errorlevel!"
if not "!RC!"=="0" (
    echo.
    echo [ERREUR] Demarrage echoue (code !RC!). Consultez logs/
    pause
    exit /b !RC!
)

echo.
echo [OK] CitéVision demarre — ouvrez http://localhost:5174
exit /b 0
