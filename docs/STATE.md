# Citévision 2.0 — Project State

**Last updated:** 2026-06-12  
**Version:** 2.0.0  
**Livrable courant:** L14 — DONE

## Statut global

| Livrable | Nom | Statut |
|----------|-----|--------|
| L1 | Fondations & infrastructure | DONE |
| L2 | Auth, RBAC, multi-tenant | DONE |
| L3 | Module caméras | DONE |
| L4 | Video Engine C++ | DONE |
| L5 | AI Core YOLO + ByteTrack | DONE |
| L6 | Zones & événements atomiques | DONE |
| L7 | Règles, comportement, corrélation | DONE |
| L8 | UI Shell premium | DONE |
| L9 | Vues opérationnelles | DONE |
| L10 | Éditeurs zones + règles | DONE |
| L11 | Alertes & MinIO | DONE |
| L12 | Face + ANPR (stubs) | DONE |
| L13 | Tests & observabilité | DONE |
| L14 | Polish, docs, GitHub | DONE (commit local) |

## Tests exécutés (2026-06-12)

| Test | Résultat |
|------|----------|
| `go test ./...` | PASS |
| `pytest ai-engine/tests/` | 15 PASS |
| `npm run build` | PASS |
| `scripts/validate.ps1` | 9/9 PASS |

## Reprise agent

1. Lire `docs/PROMPT-AGENT.md`
2. Lire ce fichier (`docs/STATE.md`)
3. Lire `docs/DECISIONS.md`
4. Démarrer Docker Desktop puis `docker compose up -d`
5. `bash scripts/start-all.sh` ou démarrer services manuellement

## Environnement

- **WSL cible:** `/home/gheno/citevision` (virtualisation à activer)
- **Windows actuel:** `C:\Users\gheno\citevision`
- **Login seed:** `admin@citevision.local` / `Citevision123!`
- **Caméra test:** variables `TEST_CAMERA_*` dans `.env` uniquement

## Actions manuelles restantes

- Régénérer PAT GitHub et mettre à jour `.env` → `git push`
- Démarrer Docker Desktop pour PostgreSQL/Redis/MQTT/MinIO
- Activer virtualisation WSL pour environnement Linux natif
