@echo off
:: Synchronise citevision-v2 → C:\CitéVision (installer + setup.bat)
set SRC=c:\Users\gheno\citevision-v2
set DST=C:\CitéVision

:: Kill any running installer server first
taskkill /F /IM python.exe /T >nul 2>&1

robocopy "%SRC%\installer" "%DST%\installer" /E /XD __pycache__ .venv /XF "*.pyc" /NFL /NJH /NJS
copy /Y "%SRC%\setup.bat" "%DST%\setup.bat" >nul
copy /Y "%SRC%\setup.sh"  "%DST%\setup.sh"  >nul 2>&1

echo [OK] Sync complete: citevision-v2 → C:\CitéVision
