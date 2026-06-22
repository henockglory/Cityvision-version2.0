# CitéVision v2 — Agent Checkpoint

**Dernière mise à jour :** implémentation plan MVP commercial (2 semaines)

## Gate qualité

```bash
cd ~/citevision-v2
bash scripts/setup-demo-kinshasa.sh      # premier démarrage / reset démo
bash scripts/validate-commercial-gate.sh # obligatoire avant livraison
```

## Livré dans cette session

| Domaine | Changement |
|---------|------------|
| GPU | `YOLO_DEVICE=cuda`, `onnxruntime-gpu`, `/health/gpu`, `validate-gpu.sh` |
| Vidéo | MP4 ext4 `data/videos/`, go2rtc, `Go2RtcPlayer` dynamique, LiveView/VideoWall |
| Caméra | `register-virtual-camera.sh` idempotent, déduplication SQL |
| RTSP | `BuildRTSP` + credentials + metadata override, orchestrateur via `camera.Service` |
| Règles | `RuleCatalogPanel`, bouton Activer, `/rules?catalog=1` |
| Zones | Chargement API, liste, suppression, overlay vidéo |
| Démo | `/demo` polish cv-*, catalogue intégré, acquittement alertes |
| API | `PATCH /alerts/{id}/acknowledge`, `DELETE /zones/{id}` |
| CI | backend Go + frontend build (plus de placeholder `web/`) |
| Docs | `docs/GPU-WSL2.md`, `docs/DEMO-MINISTERE-KINSHASA.md` |

## URLs

- App : http://localhost:5174/demo
- Login : glory.henock@hologram.cd / Hologram2026!
- go2rtc : http://localhost:1984/stream.html?src=benedicte

## Statut gate

Exécuter `validate-commercial-gate.sh` sur WSL avec stack démarrée + RTX 4050 pour statut GREEN.
