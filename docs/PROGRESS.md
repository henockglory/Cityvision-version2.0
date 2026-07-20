# Progress — CitéVision v2

**Dernière mise à jour :** 2026-07-13

## Refonte produit (plan expert)

- [x] Pass lecture — [PLATFORM-COMPREHENSION.md](./PLATFORM-COMPREHENSION.md)
- [x] Phase 0 : `/health/platform`, `preflight_platform.sh`, [ENV-PLATFORM.md](./ENV-PLATFORM.md)
- [x] Phase 4 : Frigate event-only démo, Retention Governor, `validate_disk_budget.sh`
- [x] Phase 1 : test spatial, evidence audit dans `validate_demo_five_rules.py`
- [x] Phase 2 : demo heal Frigate fresh, align 5s, executor 8×8s
- [x] Phase 3 : Supervisor, `inject_faults_test.sh`, UI health
- [x] Phase 5 : detection_classes model-pack, ClassFilterPicker dynamique
- [x] Phase 6–7 : [PRODUCT-DOD.md](./PRODUCT-DOD.md), OPERATIONS + QUICKSTART

---
- [x] `docs/CLARIFICATIONS.md` (40 questions + défauts)
- [x] Scripts Windows (`doctor-windows.ps1`, `start-windows.ps1`)
- [x] Scripts Linux/WSL (`start-linux.sh`, `doctor-linux.sh`, `sync-to-wsl.sh`)
- [x] `docs/WSL-MIGRATION.md` — méthode principale dev local

## Phase 1 — Fondations
- [x] Monorepo, Docker Compose (+ go2rtc :1984)
- [x] Schéma PG + `system_config.initialized`
- [x] `.env.example` complet (JWT, audit, camera key, go2rtc)

## Phase 2 — Vidéo & caméras
- [x] Video engine C++ (FFmpeg dual pipeline)
- [x] Probe multi-vendor (Hikvision/Dahua/generic)
- [x] go2rtc preview API `/cameras/{id}/preview`
- [ ] Test live 192.168.1.108 (nécessite Docker + réseau caméra)

## Phase 3 — IA
- [x] YOLO ONNX + ByteTrack + ResourceBudgetManager
- [x] InsightFace/PaddleOCR optionnels (vide si absent)
- [x] `scripts/download-models.ps1`

## Phase 4 — Événements & comportement
- [x] Event generator, behavior, state, correlation

## Phase 5 — Règles
- [x] rules-engine + catalogue 26 templates (5 fichiers JSON)
- [x] MQTT publish alertes sur match
- [x] API `/rules/catalog`

## Phase 6 — Backend
- [x] Setup wizard, JWT, RBAC, audit
- [x] WebSocket `/ws/alerts` + subscriber MQTT backend

## Phase 7 — Frontend
- [x] Zéro mock, wizard setup, wizard caméra 4 étapes
- [x] HologramBackground, useAlertWebSocket
- [x] Checklist visuelle 50 points (`docs/visual-checklist.md`)

## Phase 8 — Tests
- [x] Unitaires Go/Python PASS
- [x] `validate-full.ps1`, `bench-api.ps1`
- [x] Playwright smoke `tests/e2e/`
- [ ] E2E live + charge 12 flux (stack Docker requise)

## Phase 9 — Livraison
- [x] INSTALL.md WSL-first
- [x] WSL-MIGRATION.md
- [x] test-report.md mis à jour
- [ ] Tag `v2.0.1-validated` (commit/push sur demande)

## Reprise rapide (WSL)

```bash
cd ~/citevision-v2
bash scripts/start-linux.sh
```

Alternative Windows :

```powershell
cd C:\Users\gheno\citevision-v2
powershell -File scripts\start-windows.ps1
```

Première visite : http://localhost:5174/setup
