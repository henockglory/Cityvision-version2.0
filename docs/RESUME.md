# RESUME — Reprise agent IA

**Projet :** Citévision v2.0  
**Chemin :** `C:\Users\gheno\citevision-v2`  
**Remote :** https://github.com/henockglory/Cityvision-v2

## État actuel (2026-06-13)

- Stack complète scaffoldée, zéro mock validé
- **Méthode principale : WSL Ubuntu 24.04 + Docker Engine natif** (`start-linux.sh`)
- Alternative Windows : Docker Desktop + `start-windows.ps1`
- go2rtc intégré (port 1984), probe caméra multi-vendor, preview WebRTC
- 31 templates règles JSON, pipeline MQTT alertes → backend → WebSocket
- HologramBackground + sons robotiques + onboarding skippable

## Démarrer en 1 commande (WSL)

```bash
cd ~/citevision-v2
bash scripts/start-linux.sh
```

Première installation :

```bash
bash scripts/sync-to-wsl.sh   # depuis WSL
bash scripts/setup-wsl.sh
bash scripts/start-linux.sh
```

Diagnostic :

```bash
bash scripts/doctor-linux.sh
```

## Alternative Windows

```powershell
powershell -File scripts\start-windows.ps1
powershell -File scripts\doctor-windows.ps1
```

## Tests validés offline

```powershell
powershell -File scripts\validate.ps1
powershell -File scripts\validate-full.ps1 -SkipLiveStack
```

Résultats : voir `docs/test-report.md`

## Prochaines étapes si interruption

1. Vérifier WSL : `wsl -d Ubuntu-24.04 -- bash scripts/doctor-linux.sh`
2. Démarrer stack : `bash scripts/start-linux.sh` (dans `~/citevision-v2`)
3. Ouvrir http://localhost:5174/setup si DB vierge
4. Configurer caméra test dans `.env` (CAMERA_TEST_*)
5. Exécuter `validate-full.ps1` sans `-SkipLiveStack` (Windows) ou tests manuels
6. Playwright : `cd tests/e2e && npm i && npx playwright test`

## Fichiers clés modifiés récemment

| Fichier | Rôle |
|---------|------|
| `scripts/start-linux.sh` | Orchestration WSL/Linux (principal) |
| `scripts/start-windows.ps1` | Orchestration Windows (Docker Desktop) |
| `backend/internal/camera/wizard.go` | Probe RTSP |
| `backend/internal/ws/hub.go` | Alertes temps réel |
| `shared/rule-catalog/*.json` | 26 templates |
| `frontend/src/components/HologramBackground.tsx` | UX premium |

## Secrets

- Jamais committer `.env`
- Régénérer PAT GitHub si exposé
- Credentials caméra uniquement dans `.env` local
