# Citévision v2 — Rapport de tests

**Date :** 2026-06-12  
**Version :** 2.0.0-production  
**Environnement :** Windows natif (WSL cible indisponible — virtualisation à activer)

## Résumé

| Suite | Résultat | Détail |
|-------|----------|--------|
| Go backend `go test ./...` | PASS | setup + rules |
| Go rules-engine `go test ./...` | PASS | evaluator + dedup |
| Python AI `pytest` | PASS | 16/16 |
| Frontend `npm run build` | PASS | tsc + vite |
| Zéro mock frontend | PASS | aucun `mock.ts` / `demoLogin` |
| Docker infra | SKIP | Docker Desktop arrêté |

## Tests unitaires

### Backend — setup wizard
- `internal/setup` : statut `initialized=false` au démarrage
- `Complete` : crée exactement 1 org + 1 super_admin
- Rejet si déjà initialisé

### Backend — règles
- Validation définitions ET/OU/NON
- Rejet actions vides

### Rules-engine
- Évaluateur conditions composites
- Anti-déduplication fenêtre temporelle

### AI Engine
- ResourceBudgetManager (1/4/12 caméras)
- ByteTrack assignation track_id
- Modules optionnels retournent `[]` si modèle absent (pas de fausses détections)

## Tests d'intégration (manuels requis)

| Parcours | Statut | Commande |
|----------|--------|----------|
| Setup from scratch | À exécuter | `docker compose up` + API + frontend |
| Ajout caméra 192.168.1.108 | À exécuter | wizard Caméras + `.env` TEST_CAMERA_* |
| Création règle → alerte | À exécuter | après flux IA actif |

## Tests E2E

Playwright : structure dans `tests/e2e/README.md` — à exécuter post-Docker.

Parcours cible :
1. `/setup` → création org + admin
2. Login → dashboard vide (0 caméra, 0 règle, 0 alerte)
3. Wizard caméra → liste avec 1 entrée réelle

## Tests visuels

Checklist (50 points) — voir `docs/CLARIFICATIONS.md` section UX.

- [ ] Setup wizard aligné 8px grid
- [ ] Dashboard vide avec EmptyState (pas de fausses lignes)
- [ ] Thème dark + light cohérents
- [ ] Mur d'écrans vide affiche emplacements vides

## Charge

Script `scripts/validate-phase8.sh` — 12 flux simulés (à exécuter sous Linux/WSL avec GPU).

## Recommandations avant livraison client

1. Activer WSL + Docker Desktop
2. Exécuter parcours setup complet sur DB vierge
3. Tester caméra réelle 192.168.1.108
4. Télécharger modèle YOLO : `scripts/download-yolo-model.sh`
