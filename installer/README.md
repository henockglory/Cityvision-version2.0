# Installer — CitéVision v2

Assistant d'installation premium avec interface web animée. Vérifie le matériel, détecte les dépendances et installe l'environnement complet automatiquement.

## Lancer l'installer

### Windows (double-clic)

```
setup.bat
```

### Linux / macOS

```bash
chmod +x setup.sh
./setup.sh
```

L'interface s'ouvre automatiquement dans le navigateur sur `http://localhost:7315`.

## Architecture

```
installer/
├── setup-server.py      ← Serveur HTTP Python stdlib (port 7315), aucune dépendance externe
├── check-hardware.py    ← Vérification CPU/RAM/disque/GPU — retourne JSON pass/warn/fail
├── deps-checker.py      ← Vérification et installation des dépendances
├── ui/
│   ├── index.html       ← SPA d'installation (standalone, aucun build)
│   ├── styles.css       ← Design premium dark, animations CSS
│   └── app.js           ← Orchestration : splash → matériel → dépendances → installation
└── windows/
    ├── citevision-setup.nsi  ← Script NSIS pour générer setup.exe
    └── BUILD.md              ← Instructions de compilation
```

## Les 4 étapes UI

1. **Splash** — Logo animé, initialisation du diagnostic
2. **Matériel** — Grille CPU/RAM/Stockage/GPU avec indicateurs pass ✓ / warning ⚠ / fail ✗  
   + Profil GPU détecté (Tier Standard/High/Ultra/Max)
3. **Dépendances** — Checklist animée de tous les composants requis (Docker, Go, Node, Python, CUDA…)
4. **Prêt** — Animation de succès, bouton "Ouvrir CitéVision"

## APIs du serveur

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/api/hardware` | GET | Résultat complet du check hardware (JSON) |
| `/api/deps` | GET | État de toutes les dépendances (JSON) |
| `/api/install` | POST | Stream SSE de l'installation automatique |
| `/api/status` | GET | État global de préparation |
| `/api/app-status` | GET | Vérifie si l'app est déjà lancée |

## Générer setup.exe (Windows)

Voir [windows/BUILD.md](windows/BUILD.md).

Résumé :
```batch
cd installer\windows
makensis citevision-setup.nsi
```

## Prérequis pour l'installer lui-même

- **Python 3.10+** (standard library uniquement, aucun `pip install` requis)
- **Connexion Internet** (pour télécharger les dépendances manquantes)
