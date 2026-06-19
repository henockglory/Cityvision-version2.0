@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title CitéVision v2 - Assistant d'installation

:: Set UTF-8 for Python output
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo.
echo  ============================================================
echo    CitéVision v2  -  Installateur
echo    Plateforme de telesurveillance intelligente
echo  ============================================================
echo.

:: 0. Bootstrap prerequis (machine vierge)
set SENTINEL=%~dp0installer\.bootstrap_done
set NEED_BOOTSTRAP=0

:: Verifier si Python est dans le PATH
set PYTHON=
for %%P in (python3.12 python3 python py) do (
    if "!PYTHON!"=="" (
        %%P --version >nul 2>&1
        if !errorlevel! == 0 (
            set PYTHON=%%P
        )
    )
)

if "!PYTHON!"=="" (
    echo  [BOOTSTRAP] Python introuvable - demarrage du bootstrap automatique...
    set NEED_BOOTSTRAP=1
) else if not exist "!SENTINEL!" (
    echo  [BOOTSTRAP] Premiere execution detectee - verification des prerequis...
    set NEED_BOOTSTRAP=1
)

if "!NEED_BOOTSTRAP!"=="1" (
    echo  [BOOTSTRAP] Lancement de installer\windows\bootstrap.ps1 ...
    echo.

    :: Verifier si on est admin, sinon relancer avec UAC
    net session >nul 2>&1
    if !errorlevel! neq 0 (
        echo  [BOOTSTRAP] Elevation des droits administrateur requise...
        powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs -Wait"
        if !errorlevel! neq 0 (
            echo  [ERREUR] Impossible d'obtenir les droits administrateur.
            echo  Relancez setup.bat en clic droit - Executer en tant qu'administrateur
            pause
            exit /b 1
        )
        exit /b 0
    )

    :: Executer le bootstrap PowerShell et recuperer le JSON
    for /f "delims=" %%R in ('powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\windows\bootstrap.ps1" 2^>^&1') do (
        set BOOTSTRAP_OUTPUT=%%R
        echo  [BOOTSTRAP] %%R
    )

    :: Verifier si reboot requis
    echo !BOOTSTRAP_OUTPUT! | findstr /i "reboot_required.*true" >nul 2>&1
    if !errorlevel! == 0 (
        echo.
        echo  ============================================================
        echo    REDEMARRAGE REQUIS
        echo.
        echo    WSL2 a ete active sur votre systeme.
        echo    Redemarrez Windows puis relancez setup.bat.
        echo  ============================================================
        echo.
        pause
        exit /b 0
    )

    :: Rafraichir le PATH apres installation Python
    if "!PYTHON!"=="" (
        for %%P in (python3.12 python3 python py) do (
            if "!PYTHON!"=="" (
                %%P --version >nul 2>&1
                if !errorlevel! == 0 (
                    set PYTHON=%%P
                )
            )
        )
    )

    if "!PYTHON!"=="" (
        echo.
        echo  [ERREUR] Python reste introuvable apres le bootstrap.
        echo  Redemarrez Windows et relancez setup.bat.
        echo.
        pause
        exit /b 1
    )
    echo.
)

:: 1. Trouver Python (si pas encore trouve)
if "!PYTHON!"=="" (
    for %%P in (python3.12 python3 python py) do (
        if "!PYTHON!"=="" (
            %%P --version >nul 2>&1
            if !errorlevel! == 0 (
                set PYTHON=%%P
            )
        )
    )
)

if "!PYTHON!"=="" (
    echo [ERREUR] Python 3.x introuvable dans le PATH.
    echo.
    echo  Telechargez Python 3.12 sur : https://python.org/downloads/
    echo  Cochez "Add Python to PATH" lors de l'installation.
    echo.
    pause
    exit /b 1
)

:: Verifier version Python
for /f "tokens=2 delims= " %%V in ('!PYTHON! --version 2^>^&1') do set PY_VER=%%V
echo  [INFO] Python detecte : !PY_VER!

:: 2. Repertoire du script (%~dp0. corrige le bug du backslash final)
cd /d "%~dp0."

:: 3. Lancer le serveur d'installation
echo  [INFO] Demarrage du serveur d'installation (port 7315)...
echo  [INFO] L'interface s'ouvrira dans votre navigateur.
echo.
echo  Si le navigateur ne s'ouvre pas :
echo    http://localhost:7315
echo.
echo  Appuyez sur Ctrl+C pour arreter.
echo.

!PYTHON! -X utf8 installer\setup-server.py

if !errorlevel! neq 0 (
    echo.
    echo [ERREUR] Le serveur a rencontre une erreur (code !errorlevel!).
    pause
    exit /b !errorlevel!
)

endlocal
