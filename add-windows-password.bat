@echo off
:: Ouvre le guide pour ajouter un mot de passe Windows (requis si vous n avez qu un PIN)
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
echo.
echo   CitéVision - Ajouter un mot de passe Windows
echo   (obligatoire si vous vous connectez uniquement avec un PIN)
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\installer\windows\pin-password-guide.ps1"
exit /b 0
