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
echo    Plateforme de télésurveillance intelligente
echo  ============================================================
echo.

:: ── 1. Trouver Python ────────────────────────────────────────
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
    echo [ERREUR] Python 3.x introuvable dans le PATH.
    echo.
    echo  Téléchargez Python 3.12 sur : https://python.org/downloads/
    echo  Cochez "Add Python to PATH" lors de l'installation.
    echo.
    pause
    exit /b 1
)

:: ── Vérifier version Python >= 3.10 ──────────────────────────
for /f "tokens=2 delims= " %%V in ('!PYTHON! --version 2^>^&1') do set PY_VER=%%V
echo  [INFO] Python detecte : !PY_VER!

:: ── 2. Répertoire du script ───────────────────────────────────
cd /d "%~dp0"

:: ── 3. Lancer le serveur d'installation ──────────────────────
echo  [INFO] Démarrage du serveur d'installation (port 7315)...
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
