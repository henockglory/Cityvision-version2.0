# Citévision v2 — Guide de reprise rapide

**Chemin cible WSL :** `/home/gheno/citevision-v2`  
**Chemin actuel (fallback) :** `C:\Users\gheno\citevision-v2`  
**Version :** 2.0.0-production

## Différence critique vs v1

| v1 (abandonné) | v2 (actuel) |
|----------------|-------------|
| `mock.ts` + 16 caméras fictives | **Zéro mock** — EmptyState |
| `seed.go` silencieux | **Wizard `/setup`** uniquement |
| `demoLogin` | Auth API réelle |
| Ports 8080/5173 | Ports **8081/5174** |

## État actuel

- Phases 0–7 : code livré, tests unitaires PASS
- Phase 8 : rapport tests ; E2E/charge nécessitent Docker+WSL
- Phase 9 : commit local ; push Git en attente

## Démarrage rapide

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d
cd backend && go run ./cmd/api
cd frontend && npm run dev
```

→ http://localhost:5174/setup (si DB vierge)

## Fichiers clés

| Fichier | Rôle |
|---------|------|
| `docs/CLARIFICATIONS.md` | 35 décisions produit |
| `docs/PROGRESS.md` | Avancement phases |
| `backend/internal/setup/service.go` | Wizard première install |
| `frontend/src/components/SetupGuard.tsx` | Redirection setup |
| `frontend/src/components/EmptyState.tsx` | Listes vides |

## Blocages connus

1. **WSL** : virtualisation désactivée (`HCS_E_HYPERV_NOT_INSTALLED`)
2. **Docker Desktop** : doit être démarré pour infra
3. **Caméra test** : credentials dans `.env` local uniquement

## Prochaine action agent

1. Activer WSL
2. `docker compose up` + parcours setup E2E
3. Test caméra 192.168.1.108
4. Push `henockglory/Cityvision-v2` tag `v2.0.0-production`
