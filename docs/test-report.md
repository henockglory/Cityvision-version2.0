# Test Report — Citévision v2

**Date:** 2026-06-13  
**Environnement:** Windows 10, sans WSL (Docker Desktop requis pour stack live)

## Tests unitaires et build (exécutés)

| Test | Résultat | Détail |
|------|----------|--------|
| Backend Go tests | PASS | setup, rules |
| Rules-engine Go tests | PASS | dedup, evaluator |
| AI engine pytest | PASS | 16/16 |
| Frontend build | PASS | Vite ~5s |
| Zéro mock | PASS | aucun mock.ts, demoLogin |
| Catalogue règles 20+ | PASS | 26 templates JSON |
| Backend compile | PASS | go build cmd/api |
| Rules-engine compile | PASS | go build cmd/rules-engine |

## Tests live (nécessitent `start-windows.ps1`)

| Test | Statut | Commande |
|------|--------|----------|
| F1 API health | À exécuter | `validate-full.ps1` |
| F2 Setup wizard | À exécuter | POST /api/v1/setup/complete |
| F3 Dashboard vide | À exécuter | après setup |
| F4 Caméra 192.168.1.108 | À exécuter | wizard + probe |
| F5 Zones/lignes | À exécuter | API spatial |
| F8 MQTT → alerte → WS | À exécuter | rules-engine + backend |
| Playwright E2E | À exécuter | `cd tests/e2e && npm i && npm test` |
| Charge 12 flux | À exécuter | GPU + caméras |

## Performance (offline build)

| Métrique | Cible | Mesuré |
|----------|-------|--------|
| Frontend build | < 60s | ~5s PASS |
| AI pytest | < 5s | ~0.7s PASS |
| API health p95 | < 200ms | bench-api.ps1 avec stack |

## Esthétique

Checklist 50 points: [visual-checklist.md](visual-checklist.md)

## Commandes de reprise

```powershell
powershell -File scripts\doctor-windows.ps1
powershell -File scripts\start-windows.ps1
powershell -File scripts\validate-full.ps1
```
