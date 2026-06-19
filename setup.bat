@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title CitéVision v2 - Assistant d'installation

:: UTF-8 for Python output
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo.
echo  ============================================================
echo    CitéVision v2  -  Installateur
echo    Plateforme de telesurveillance intelligente
echo  ============================================================
echo.

:: Safe entry into script directory (%~dp0. avoids trailing-backslash quote bug)
pushd "%~dp0." >nul 2>&1
if errorlevel 1 (
    echo  [ERREUR] Impossible d'acceder au repertoire du script.
    echo           Chemin: %~dp0
    pause
    exit /b 1
)

:: ── 0. Bootstrap prérequis (machine vierge) ───────────────────
set "SENTINEL=installer\.bootstrap_done"
set NEED_BOOTSTRAP=0

:: Vérifier si Python est dans le PATH
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
    echo  [BOOTSTRAP] Python introuvable — demarrage du bootstrap automatique...
    set NEED_BOOTSTRAP=1
) else if not exist "!SENTINEL!" (
    echo  [BOOTSTRAP] Premiere execution detectee — verification des prerequis...
    set NEED_BOOTSTRAP=1
)

if "!NEED_BOOTSTRAP!"=="1" (
    echo  [BOOTSTRAP] Lancement de installer\windows\bootstrap.ps1 ...
    echo.

    :: Admin requis pour WSL2 — relancer ce script en élevé (sans quoting fragile)
    net session >nul 2>&1
    if !errorlevel! neq 0 (
        echo  [BOOTSTRAP] Elevation des droits administrateur requise...
        echo  [BOOTSTRAP] Acceptez la fenetre UAC pour continuer.
        echo.
        powershell -NoProfile -ExecutionPolicy Bypass -Command ^
            "Start-Process -FilePath '%~f0' -Verb RunAs -Wait"
        if !errorlevel! neq 0 (
            echo.
            echo  [ERREUR] Impossible d'obtenir les droits administrateur.
            echo  Relancez setup.bat : clic droit -^> Executer en tant qu'administrateur
            pause
            popd
            exit /b 1
        )
        popd
        exit /b 0
    )

    :: Exécuter le bootstrap PowerShell
    set BOOTSTRAP_OUTPUT=
    for /f "delims=" %%R in ('powershell -NoProfile -ExecutionPolicy Bypass -File "installer\windows\bootstrap.ps1" 2^>^&1') do (
        set BOOTSTRAP_OUTPUT=%%R
        echo  [BOOTSTRAP] %%R
    )

    :: Reboot requis (WSL2 activé)
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
        popd
        exit /b 0
    )

    :: Rafraîchir Python après bootstrap
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
        popd
        exit /b 1
    )
    echo.
)

:: ── 1. Trouver Python (si pas encore trouvé) ──────────────────
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
    popd
    exit /b 1
)

for /f "tokens=2 delims= " %%V in ('!PYTHON! --version 2^>^&1') do set PY_VER=%%V
echo  [INFO] Python detecte : !PY_VER!

:: ── 2. Lancer le serveur d'installation ──────────────────────
echo  [INFO] Demarrage du serveur d'installation (port 7315)...
echo  [INFO] L'interface s'ouvrira dans votre navigateur.
echo.
echo  Si le navigateur ne s'ouvre pas :
echo    http://localhost:7315
echo.
echo  Appuyez sur Ctrl+C pour arreter.
echo.

if not exist "installer\setup-server.py" (
    echo  [ERREUR] Fichier introuvable : installer\setup-server.py
    echo  Verifiez que le projet est complet dans : %CD%
    pause
    popd
    exit /b 1
)

!PYTHON! -X utf8 installer\setup-server.py

if !errorlevel! neq 0 (
    echo.
    echo [ERREUR] Le serveur a rencontre une erreur (code !errorlevel!).
    pause
    popd
    exit /b !errorlevel!
)

popd
endlocal
