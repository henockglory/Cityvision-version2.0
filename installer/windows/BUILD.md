# Compiler l'installateur Windows CitéVision (.exe)

## Prérequis

- **NSIS 3.09+** — [nsis.sourceforge.io](https://nsis.sourceforge.io/Download) (gratuit, open source)
- Windows 10+ (ou Wine sur Linux)

## Étapes

### 1. Installer NSIS

Téléchargez et installez NSIS depuis https://nsis.sourceforge.io/Download.  
Cochez l'option "Add NSIS to PATH" lors de l'installation.

### 2. Vérifier la structure du projet

Assurez-vous d'être dans le dossier racine du projet (`citevision-v2/`) et que tous les fichiers sont présents.

### 3. Compiler

```batch
cd installer\windows
makensis citevision-setup.nsi
```

Ou depuis la racine du projet :

```batch
makensis installer\windows\citevision-setup.nsi
```

### 4. Résultat

Le fichier `CitéVision-v2-Setup.exe` est généré dans `installer\windows\`.

## Personnalisation

| Option | Fichier | Valeur par défaut |
|--------|---------|-------------------|
| Dossier d'installation | `citevision-setup.nsi` | `C:\CitéVision` |
| Icône | `citevision-setup.nsi` | `frontend/public/favicon.ico` |
| Langue | `citevision-setup.nsi` | Français + Anglais |

## Distribution

Le fichier `CitéVision-v2-Setup.exe` est autonome et peut être distribué directement.  
L'installateur extrait le projet, installe WSL2 si absent, et lance l'assistant de configuration.

## Remarques

- L'installateur nécessite les **droits administrateur** (pour WSL2 et les raccourcis système).
- **WSL2** est installé automatiquement si absent (nécessite un redémarrage Windows).
- **Python 3.12** doit être installé manuellement par l'utilisateur s'il est absent.
- Un **raccourci sur le Bureau** et dans le **Menu Démarrer** est créé automatiquement.
