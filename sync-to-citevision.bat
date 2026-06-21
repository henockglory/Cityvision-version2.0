@echo off
:: Synchronise citevision_optimized -> C:\Citevision (deploiement / tests ASCII path)
setlocal EnableDelayedExpansion
set "SRC=c:\Users\gheno\citevision_optimized"
set "DST=C:\Citevision"

echo [SYNC] Arret du serveur installateur (port 7315)...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":7315" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%P >nul 2>&1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SRC%\scripts\sync-from-optimized.ps1" -Targets "%DST%"
set "RC=!errorlevel!"
if !RC! geq 8 set RC=1

echo.
if !RC! equ 0 (
    echo [OK] citevision_optimized -^> %DST%
) else (
    echo [WARN] Sync termine avec avertissements robocopy (code !RC!)
)
endlocal
exit /b 0
