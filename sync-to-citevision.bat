@echo off
:: Synchronise citevision-v2 -> C:\Citevision (projet complet pour tests/deploiement)
:: NOTE: pas d'accent dans le chemin DST pour eviter les corruptions CP850/UTF-8
setlocal EnableDelayedExpansion
set "SRC=c:\Users\gheno\citevision-v2"
set "DST=C:\Citevision"

echo [SYNC] Arret du serveur installateur (port 7315)...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":7315" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%P >nul 2>&1
)

echo [SYNC] Ecriture installer\.build_version...
pushd "%SRC%"
git rev-parse --short HEAD > installer\.build_version 2>nul
if errorlevel 1 echo unknown> installer\.build_version
for /f %%D in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-ddTHH:mmZ"') do echo %%D>> installer\.build_version
popd

set "ROBO=/E /XD node_modules .venv __pycache__ logs .git /XF *.pyc /XJ /R:0 /W:0"
set "DIRS=backend frontend ai-engine rules-engine infra shared docs installer scripts"

echo [SYNC] citevision-v2 -^> %DST%
for %%D in (%DIRS%) do (
    if exist "%SRC%\%%D" (
        robocopy "%SRC%\%%D" "%DST%\%%D" %ROBO% /NFL /NJH /NJS >nul
    )
)

if exist "%SRC%\.env.example" copy /Y "%SRC%\.env.example" "%DST%\.env.example" >nul
if exist "%SRC%\Makefile" copy /Y "%SRC%\Makefile" "%DST%\Makefile" >nul
if exist "%SRC%\docker-compose.yml" copy /Y "%SRC%\docker-compose.yml" "%DST%\docker-compose.yml" >nul
for %%F in (docker-compose*.yml) do (
    if exist "%SRC%\%%F" copy /Y "%SRC%\%%F" "%DST%\%%F" >nul
)

:: Copier et normaliser les .bat en CRLF UTF-8 sans BOM (evite 'tle'/'cho'/'et' CMD)
for %%F in (setup.bat sync-to-citevision.bat register-service.bat) do (
    if exist "%SRC%\%%F" (
        copy /Y "%SRC%\%%F" "%DST%\%%F" >nul 2>&1
        powershell -NoProfile -Command ^
            "$p='%DST:\=\\%\%%F'; $c=[IO.File]::ReadAllText($p); $c=$c -replace '`r`n','`n' -replace '`n','`r`n'; [IO.File]::WriteAllText($p,$c,[Text.UTF8Encoding]::new($false))"
    )
)
copy /Y "%SRC%\setup.sh"  "%DST%\setup.sh"  >nul 2>&1
if exist "%SRC%\installer\.bootstrap_done" (
    copy /Y "%SRC%\installer\.bootstrap_done" "%DST%\installer\.bootstrap_done" >nul 2>&1
)

echo [OK] Sync complete.
endlocal
