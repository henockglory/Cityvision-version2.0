@echo off
:: Synchronise citevision-v2 -> C:\CiteVision (projet complet pour tests/deploiement)
setlocal
set "SRC=c:\Users\gheno\citevision-v2"
set "DST=C:\CitéVision"

echo [SYNC] Arret du serveur installateur (port 7315)...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":7315" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%P >nul 2>&1
)

echo [SYNC] citevision-v2 -^> %DST%
robocopy "%SRC%\installer" "%DST%\installer" /E /XD __pycache__ .venv /XF "*.pyc" /NFL /NJH /NJS
robocopy "%SRC%\scripts"   "%DST%\scripts"   /E /XD __pycache__ /XF "*.pyc" /NFL /NJH /NJS
copy /Y "%SRC%\setup.bat" "%DST%\setup.bat" >nul
powershell -NoProfile -Command "$p='%DST:\=\\%\setup.bat'; $c=[IO.File]::ReadAllText($p); $c=$c -replace \"`r`n\",\"`n\" -replace \"`n\",\"`r`n\"; [IO.File]::WriteAllText($p,$c,[Text.UTF8Encoding]::new($false))"
copy /Y "%SRC%\setup.sh"  "%DST%\setup.sh"  >nul 2>&1
copy /Y "%SRC%\sync-to-citevision.bat" "%DST%\sync-to-citevision.bat" >nul 2>&1
if exist "%SRC%\installer\.bootstrap_done" (
    copy /Y "%SRC%\installer\.bootstrap_done" "%DST%\installer\.bootstrap_done" >nul 2>&1
)

echo [OK] Sync complete.
endlocal
