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

:: ── 0. Bootstrap prérequis (machine vierge) ───────────────────
set SENTINEL=%~dp0installer\.bootstrap_done
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
    echo  [BOOTSTRAP] Python introuvable — démarrage du bootstrap automatique...
    set NEED_BOOTSTRAP=1
) else if not exist "!SENTINEL!" (
    echo  [BOOTSTRAP] Première exécution détectée — vérification des prérequis...
    set NEED_BOOTSTRAP=1
)

if "!NEED_BOOTSTRAP!"=="1" (
    echo  [BOOTSTRAP] Lancement de installer\windows\bootstrap.ps1 ...
    echo.

    :: Vérifier si on est admin, sinon relancer avec UAC
    net session >nul 2>&1
    if !errorlevel! neq 0 (
        echo  [BOOTSTRAP] Élévation des droits administrateur requise...
        powershell -NoProfile -ExecutionPolicy Bypass -Command ^
            "Start-Process cmd -ArgumentList '/c cd /d ""%~dp0"" && setup.bat' -Verb RunAs -Wait"
        if !errorlevel! neq 0 (
            echo  [ERREUR] Impossible d'obtenir les droits administrateur.
            echo  Relancez setup.bat en cliquant droit → Exécuter en tant qu'administrateur
            pause
            exit /b 1
        )
        exit /b 0
    )

    :: Exécuter le bootstrap PowerShell et récupérer le JSON
    for /f "delims=" %%R in ('powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\windows\bootstrap.ps1" 2^>^&1') do (
        set BOOTSTRAP_OUTPUT=%%R
        echo  [BOOTSTRAP] %%R
    )

    :: Vérifier si reboot requis
    echo !BOOTSTRAP_OUTPUT! | findstr /i "reboot_required.*true" >nul 2>&1
    if !errorlevel! == 0 (
        echo.
        echo  ╔══════════════════════════════════════════════════════════╗
        echo  ║  REDÉMARRAGE REQUIS                                      ║
        echo  ║                                                          ║
        echo  ║  WSL2 a été activé sur votre système.                   ║
        echo  ║  Veuillez REDÉMARRER Windows puis relancer setup.bat.   ║
        echo  ╚══════════════════════════════════════════════════════════╝
        echo.
        pause
        exit /b 0
    )

    :: Rafraîchir le PATH après installation Python
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
        echo  [ERREUR] Python reste introuvable après le bootstrap.
        echo  Redémarrez Windows et relancez setup.bat.
        echo.
        pause
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

:: ── 2b. Enregistrement service Windows CitéVision ─────────────
echo  [INFO] Vérification du service Windows CitéVision...
sc query "CitéVision" >nul 2>&1
if !errorlevel! neq 0 (
    echo  [INFO] Enregistrement du service Windows...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\windows\install-service.ps1" 2>&1
    if !errorlevel! == 0 (
        echo  [OK] Service Windows enregistre avec succes.
    ) else (
        echo  [WARN] Enregistrement service echoue (droits admin requis ?).
        echo         L'application fonctionne quand meme sans service Windows.
    )
) else (
    echo  [OK] Service Windows CitéVision deja enregistre.
)
echo.

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
