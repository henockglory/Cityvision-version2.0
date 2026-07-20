# Rapport de correction — Alignement preuves live (post-handoff)

**Date** : 2026-07-08
**Suite de** : `docs/HANDOFF-EVIDENCE-ALIGNMENT.md`
**Contexte** : caméra 108 inaccessible ; validation par tests unitaires, E2E synthétique, audit stockage.

---

## 1. Cause racine finale

Trois défauts distincts se combinaient pour produire des crops sur route vide :

1. **`bbox` et `bbox_ts` ne voyageaient pas ensemble** dans `pipeline.py`. Le candidat
   `(evt.bbox, frame_wall_ts)` associait la bbox de zone_speed (collectée à l'instant T
   dans la zone) au timestamp de la **frame d'émission** (T + plusieurs centaines de ms,
   véhicule déjà sorti). La capture cherchait donc la frame au mauvais instant.
2. **L'historique `_bbox_history` pouvait remplacer la bbox moteur** si son score
   géométrique était meilleur — une bbox « mieux notée » d'un autre instant est
   exactement ce qui produit un cadre bleu sur route vide.
3. **La résolution de frame se faisait dans le thread asynchrone**, après le retour
   du thread inference — sans garde-fou de contenu : une frame sans véhicule dans la
   bbox partait telle quelle en MinIO avec `evidence_status=complete`.

## 2. Correctifs livrés

| Fichier | Changement |
|---------|------------|
| `evidence/capture.py` | Nouvelle fonction `select_live_event_bbox` : la bbox moteur (avec son `bbox_ts` source) **gagne toujours** quand elle est valide ; track courant / historique seulement en secours. |
| `pipeline.py` | La boucle événements live utilise `select_live_event_bbox` (remplace le pick score-only qui perdait le ts source). `_link_plates_to_violations` corrigé (accès classe au lieu d'instance). |
| `evidence/service.py` | `resolve_aligned_frame` : résolution de frame **synchrone** (dans le thread inference, ring buffer encore chaud) + garde-fou `bbox_region_has_content` avec retry sur les 6 frames voisines de `bbox_ts`. Crops/clip/upload restent asynchrones (pas de blocage ffmpeg/HTTP). Métadonnées enrichies : `capture_source=live`, `bbox_quality_ok`. |
| `evidence/service.py` | Si la bbox reste vide après retries : `evidence_status=partial` forcé — plus jamais de faux « complete ». |
| `evidence/buffer.py` | `get_frames_near_ts` : frames triées par proximité temporelle pour le retry qualité. |
| `analytics/zone_speed.py` | Mode edge-pair : mise à jour `_best_bbox` uniquement in-zone, restructurée pour ne plus masquer la détection de sortie (bug elif). |
| `ingest/segment_cycle_worker.py` | Import `priority_zone_skip` déplacé en local (cassait un import circulaire pipeline↔ingest). |
| `frontend EvidenceViewer.tsx` + i18n | Bandeau d'avertissement si `capture_source=segment` (preuve legacy) ou `bbox_quality_ok=false` (cible non confirmée). |
| `scripts/audit_evidence_quality.py` | Audit lecture seule DB+MinIO, classes H1–H4, export CSV. |

## 3. Résultats tests

```
tests/ (suite complète ai-engine, WSL venv) : 122 passed
  dont nouveaux :
  - test_live_evidence_alignment.py  (10 tests : sélection bbox, garde-fou, statut partial)
  - test_speed_evidence_e2e.py       (3 tests  : traversée synthétique → speeding →
                                      preuve alignée, crop avec véhicule, clip ftyp)
frontend : npx tsc --noEmit → 0 erreur
```

Le test E2E reproduit exactement le scénario d'échec historique : frame d'émission =
véhicule déjà sorti du cadre. La capture récupère la frame in-zone du ring buffer et le
crop subject contient bien le véhicule (Laplacian > 50, pixels véhicule présents).

## 4. Checklist §10 — état

| Section | État | Notes |
|---------|------|-------|
| A1–A4 environnement | ✅ | `frozenset()` vide, 1 seul uvicorn, health CUDA ok, caméras live (`frames_read`, pas de `segment_cycle`) |
| B1–B5 alignement | ✅ | Couvert par tests unitaires + E2E synthétique |
| C1–C5 qualité images | ✅ | Validé en synthétique ; C3 = `missing_roles` + message UI existant |
| D1, D3 clip | ✅ | Clip ≥ 1 Ko, `ftyp`, centré `bbox_ts` (E2E + code existant) |
| D2 ffprobe ≥ 24 frames | ⚠️ | Non vérifiable : les vidéos démo actuelles ne déclenchent pas de speeding (voir §6) |
| E1–E2 stockage | ✅ | Asset subject servi par l'API (41 Ko JPEG), `evidence_snapshot.package` peuplé |
| E3 UI loadFailed | ⚠️ | Médias servis OK par l'API ; vérification navigateur à faire à la prochaine session UI |
| E4 audit | ✅ | Exécuté ; base de comparaison pour les prochains événements live |
| F1–F4 preuves historiques | ✅ | CSV archivé, badge UI legacy, doc §5 ci-dessous |
| G1 flux sans trou | ✅ | Segment mode désactivé partout |
| G2 non-régression 5 règles | ✅ | Suite complète verte (feux, comptage, téléphone, ceinture inchangés) |
| G3 limite vitesse zone 108 | ❌ **Action utilisateur** | Encore à 1 km/h (test). [P.135] interdit l'écriture DB automatique → à remettre à 30 km/h via ZoneEditor |
| G4 mail premium Mailhog | ⚠️ | Non testé (aucun nouvel événement speeding déclenché, voir §6) |

## 5. Preuves historiques ratées (audit du 2026-07-08)

Sur les 100 derniers événements speeding : **84 H1 (segment)**, **16 OK** (live).
Sur les 60 derniers : 44 H1, 5 H4 (complete mais subject sans texture), 11 OK.

- Les preuves `capture_source=segment` sont **non régénérables** (MP4 sources supprimés
  après cycle). L'UI les signale désormais comme legacy.
- Les anciennes alertes peuvent donc afficher des images vides : c'est attendu et
  désormais étiqueté — aucune promesse de re-capture rétroactive.
- Rapport détaillé : `scripts/evidence_audit_report.csv` (WSL).

## 6. Limites connues

1. **Pas de validation terrain speeding** : les vidéos démo en place ne produisent pas
   de traversée de zone speed_measurement (bus statique dans la zone, flux dense en
   haut de cadre hors zone). La preuve bout-en-bout sur flux réel devra être refaite
   dès qu'une caméra RTSP ou une vidéo démo adaptée est disponible — le test E2E
   synthétique couvre le mécanisme complet en attendant.
2. **G3** : limite 1 km/h sur `Zone_distance_parcourue_108` à corriger via ZoneEditor
   (caméra hors ligne, donc sans effet immédiat).
3. **Plaque** : le crop plaque reste dépendant de la résolution du ring buffer JPEG
   (qualité 82). L'option frame BGR native (§9.4 handoff) n'a pas été implémentée —
   à considérer si l'OCR plaque reste insuffisant.
4. **Segment mode** : non réactivé, conformément au handoff. Le code reste présent
   mais hors chemin runtime.

## 7. Comment vérifier après le prochain flux réel

```bash
# 10 événements speeding consécutifs sans subject vide (DoD #2)
python3 ~/citevision-v2/scripts/audit_evidence_quality.py --limit 10
# → attendre 0 × H4 et bbox_quality_ok=true sur les nouveaux events
```
