; ─────────────────────────────────────────────────────────────
; CitéVision v2 — Script NSIS
; Génère : CitéVision-v2-Setup.exe
; Compile avec : makensis citevision-setup.nsi
; ─────────────────────────────────────────────────────────────

Unicode True
Name "CitéVision v2"
OutFile "CiteVision-v2-Setup.exe"
; ASCII install path (no accent) to avoid CP850/UTF-8 corruption in .bat scripts.
InstallDir "C:\Citevision"
InstallDirRegKey HKLM "Software\CitéVision" "Install_Dir"
RequestExecutionLevel admin
SetCompressor /SOLID lzma
SetCompress auto

; ── Inclusions NSIS ──────────────────────────────────────────
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "WinMessages.nsh"

; ── Interface MUI ─────────────────────────────────────────────
!define MUI_ABORTWARNING
!define MUI_ICON   "..\..\frontend\public\favicon.ico"
!define MUI_UNICON "..\..\frontend\public\favicon.ico"

!define MUI_HEADERIMAGE
!define MUI_BGCOLOR    "080E1A"
!define MUI_TEXTCOLOR  "F1F5F9"
!define MUI_WELCOMEFINISHPAGE_BITMAP_NOSTRETCH

; Titre des pages
!define MUI_WELCOMEPAGE_TITLE "CitéVision v2"
!define MUI_WELCOMEPAGE_TEXT  "Bienvenue dans l'assistant d'installation de CitéVision v2, la plateforme d'analyse vidéo intelligente.$\r$\n$\r$\nCe programme va :$\r$\n• Extraire CitéVision vers C:\Citevision$\r$\n• Vérifier et installer WSL2 (Ubuntu 24.04)$\r$\n• Créer un raccourci sur le Bureau$\r$\n• Lancer l'assistant de configuration$\r$\n$\r$\nCliquez sur Suivant pour continuer."

!define MUI_FINISHPAGE_TITLE  "Installation terminée"
!define MUI_FINISHPAGE_TEXT   "CitéVision v2 a été installé avec succès.$\r$\n$\r$\nL'assistant de configuration va maintenant s'ouvrir dans votre navigateur pour finaliser la configuration : création de l'organisation, des utilisateurs et des caméras."
!define MUI_FINISHPAGE_RUN    "$INSTDIR\setup.bat"
!define MUI_FINISHPAGE_RUN_TEXT "Lancer CitéVision (configuration initiale)"

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Pages désinstallation
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Langues
!insertmacro MUI_LANGUAGE "French"
!insertmacro MUI_LANGUAGE "English"

; ── Version Info ─────────────────────────────────────────────
VIProductVersion "2.0.0.0"
VIAddVersionKey /LANG=1036 "ProductName"      "CitéVision"
VIAddVersionKey /LANG=1036 "CompanyName"      "CitéVision"
VIAddVersionKey /LANG=1036 "FileVersion"      "2.0.0"
VIAddVersionKey /LANG=1036 "ProductVersion"   "2.0.0"
VIAddVersionKey /LANG=1036 "FileDescription"  "CitéVision v2 — Installer"
VIAddVersionKey /LANG=1036 "LegalCopyright"   "© 2024 CitéVision"

; ── Section principale ────────────────────────────────────────
Section "CitéVision v2 (requis)" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"

  ; Extraction des fichiers
  File /r "..\..\" 

  ; Clés de registre
  WriteRegStr HKLM "Software\CitéVision" "Install_Dir" "$INSTDIR"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\CitéVision" \
    "DisplayName"    "CitéVision v2"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\CitéVision" \
    "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\CitéVision" \
    "DisplayVersion"  "2.0.0"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\CitéVision" \
    "Publisher"       "CitéVision"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\CitéVision" \
    "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\CitéVision" \
    "NoRepair"  1

  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; Raccourci Bureau
  CreateShortCut "$DESKTOP\CitéVision.lnk" \
    "$INSTDIR\setup.bat" "" \
    "$INSTDIR\frontend\public\favicon.ico" 0 \
    SW_SHOWMINIMIZED "" "Lancer CitéVision v2"

  ; Raccourci Menu Démarrer
  CreateDirectory "$SMPROGRAMS\CitéVision"
  CreateShortCut "$SMPROGRAMS\CitéVision\CitéVision.lnk" \
    "$INSTDIR\setup.bat" "" \
    "$INSTDIR\frontend\public\favicon.ico" 0
  CreateShortCut "$SMPROGRAMS\CitéVision\Désinstaller CitéVision.lnk" \
    "$INSTDIR\uninstall.exe"

SectionEnd

; ── Section WSL2 ─────────────────────────────────────────────
Section "WSL2 + Ubuntu 24.04" SecWSL
  DetailPrint "Vérification de WSL2…"
  
  ; Check WSL
  ExecWait 'wsl --status' $R0
  ${If} $R0 != 0
    DetailPrint "Installation de WSL2 et Ubuntu 24.04…"
    DetailPrint "(Un redémarrage peut être nécessaire)"
    ExecWait 'wsl --install -d Ubuntu-24.04 --no-launch'
  ${Else}
    DetailPrint "WSL2 déjà installé."
    ; Ensure Ubuntu 24.04 is available
    ExecWait 'wsl --install -d Ubuntu-24.04 --no-launch'
  ${EndIf}
SectionEnd

; ── Section Python (vérification) ────────────────────────────
Section "Python 3.12 (vérification)" SecPython
  DetailPrint "Vérification de Python…"
  ExecWait 'python --version' $R0
  ${If} $R0 != 0
    DetailPrint "Python non trouvé — ouverture de la page de téléchargement…"
    ExecShell "open" "https://python.org/downloads/release/python-3120/"
    MessageBox MB_OK|MB_ICONINFORMATION \
      "Python 3.12 n'a pas été trouvé.$\r$\nLa page de téléchargement s'est ouverte dans votre navigateur.$\r$\n$\r$\nInstallez Python 3.12, cochez 'Add Python to PATH', puis relancez CitéVision."
  ${Else}
    DetailPrint "Python trouvé."
  ${EndIf}
SectionEnd

; ── Section Descriptions ──────────────────────────────────────
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain}   "Fichiers principaux de CitéVision v2 (requis)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecWSL}    "WSL2 avec Ubuntu 24.04 pour les services Linux (Docker, backend, AI engine)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecPython} "Python 3.12 est requis pour l'assistant d'installation et l'AI engine"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ── Désinstallation ───────────────────────────────────────────
Section "Uninstall"
  ; Arrêter les services Docker si en cours
  ExecWait 'docker compose -f "$INSTDIR\docker-compose.yml" down --timeout 10'

  ; Supprimer les fichiers
  RMDir /r "$INSTDIR"

  ; Supprimer les raccourcis
  Delete "$DESKTOP\CitéVision.lnk"
  RMDir /r "$SMPROGRAMS\CitéVision"

  ; Supprimer les clés de registre
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\CitéVision"
  DeleteRegKey HKLM "Software\CitéVision"

  MessageBox MB_OK "CitéVision v2 a été désinstallé.$\r$\nNote : WSL2 et Ubuntu restent installés sur votre système."
SectionEnd
