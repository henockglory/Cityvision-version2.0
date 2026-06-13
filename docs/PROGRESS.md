# Progress — Citévision v2

**Dernière mise à jour :** 2026-06-12

## Phase 0 — Clarifications
- [x] `docs/CLARIFICATIONS.md` (35 questions + défauts)
- [x] `PROGRESS.md`, `OPEN_QUESTIONS.md`, `RESUME.md`
- [x] `scripts/check-wsl.sh` (WSL indisponible — virtualisation à activer)

## Phase 1 — Fondations
- [x] Monorepo structure
- [x] Docker Compose (ports isolés)
- [x] Schéma PG + `system_config.initialized`
- [x] CI GitHub Actions
- [x] `.env.example`, `.gitignore` strict

## Phase 2 — Vidéo & caméras
- [x] Video engine C++ (FFmpeg dual pipeline)
- [x] API caméra discovery + wizard
- [x] vendor/README (go2rtc, ByteTrack, ONVIF)
- [ ] Test live 192.168.1.108 (nécessite Docker + réseau)

## Phase 3 — IA
- [x] YOLO ONNX + ByteTrack
- [x] ResourceBudgetManager
- [x] InsightFace/PaddleOCR optionnels (vide si absent)
- [x] MQTT publisher
- [ ] TensorRT optimisation (optionnel GPU)

## Phase 4 — Événements & comportement
- [x] Event generator (zone, line, loitering)
- [x] Behavior heuristics, state, correlation
- [x] API zones/lignes backend

## Phase 5 — Règles
- [x] rules-engine Go (ET/OU/NON, dedup)
- [x] Catalogue templates JSON (inactifs)
- [x] Rule Builder UI
- [ ] Mode canary UI complet

## Phase 6 — Backend
- [x] Setup wizard API (zéro seed auto)
- [x] Auth JWT + Redis + RBAC 7 rôles
- [x] Audit HMAC + Prometheus

## Phase 7 — Frontend
- [x] Zéro mock — EmptyState / ErrorState
- [x] Wizard `/setup`
- [x] Design premium cyberpunk
- [x] i18n fr/en

## Phase 8 — Tests
- [x] Unitaires Go/Python PASS
- [x] `docs/test-report.md`
- [ ] E2E Playwright (structure prête)
- [ ] Charge 12 flux (nécessite WSL/GPU)

## Phase 9 — Livraison
- [x] Documentation INSTALL/OPERATIONS/ARCHITECTURE
- [ ] Push Git `Cityvision-v2` tag `v2.0.0-production`

## Principe validé

**Première utilisation = DB vide → wizard → dashboard vide.** Aucune caméra/règle/utilisateur pré-créé.
