#!/usr/bin/env python3
"""
R1 – Tagger les templates partiels dans les catalogues JSON avec:
  - partial_status: "requires_calibration" | "requires_ocr" | "requires_face_ai" | "partial_aggregate" | "full"
  - partial_reason_fr: description courte pour l'UI (badge tooltip)
Exécuter depuis ~/citevision-v2
"""
import json
import glob
import sys
from pathlib import Path

# Mapping des templates partiels identifiés lors de l'audit Phase 1/3
PARTIAL_TAGS = {
    # ── Calibration vitesse requise ─────────────────────────────────────────
    "tpl-speeding": {
        "partial_status": "requires_calibration",
        "partial_reason_fr": "Nécessite une calibration caméra (homographie) pour mesurer la vitesse en km/h"
    },
    "tpl-speed-threshold": {
        "partial_status": "requires_calibration",
        "partial_reason_fr": "Nécessite une calibration caméra (homographie) pour mesurer la vitesse en km/h"
    },
    "tpl-slow-vehicle": {
        "partial_status": "requires_calibration",
        "partial_reason_fr": "Nécessite une calibration caméra pour estimer les vitesses relatives"
    },
    "tpl-sudden-stop": {
        "partial_status": "requires_calibration",
        "partial_reason_fr": "Nécessite une calibration caméra pour détecter les variations de vitesse"
    },
    "tpl-speeding-premium": {
        "partial_status": "requires_calibration",
        "partial_reason_fr": "Nécessite une calibration caméra (homographie) + module ANPR optionnel"
    },
    "tpl-traffic-pipeline": {
        "partial_status": "requires_calibration",
        "partial_reason_fr": "Pipeline multi-étapes : nécessite calibration vitesse + module ANPR (PaddleOCR)"
    },
    "tpl-accident-composite": {
        "partial_status": "requires_calibration",
        "partial_reason_fr": "Détection composite : nécessite calibration caméra pour les métriques de vitesse"
    },

    # ── Module OCR (PaddleOCR) requis ────────────────────────────────────────
    "tpl-plate-unknown": {
        "partial_status": "requires_ocr",
        "partial_reason_fr": "Nécessite le module PaddleOCR (non installé par défaut)"
    },
    "tpl-plate-wanted": {
        "partial_status": "requires_ocr",
        "partial_reason_fr": "Nécessite le module PaddleOCR + liste de plaques configurée"
    },
    "tpl-plate-watchlist": {
        "partial_status": "requires_ocr",
        "partial_reason_fr": "Nécessite le module PaddleOCR + liste de surveillance plaques"
    },

    # ── Module IA visage (InsightFace) requis ────────────────────────────────
    "tpl-face-watchlist": {
        "partial_status": "requires_face_ai",
        "partial_reason_fr": "Nécessite le module InsightFace (non installé par défaut)"
    },
    "tpl-face-unknown": {
        "partial_status": "requires_face_ai",
        "partial_reason_fr": "Nécessite le module InsightFace + base de données de visages"
    },

    # ── Agrégats non émis par l'IA standard ─────────────────────────────────
    "tpl-bottleneck": {
        "partial_status": "partial_aggregate",
        "partial_reason_fr": "Détection de goulot d'étranglement : agrégat flow_bottleneck pas encore émis par l'IA standard"
    },
    "tpl-flow-rate": {
        "partial_status": "partial_aggregate",
        "partial_reason_fr": "Débit piéton/véhiculaire : agrégat flow_rate pas encore émis par l'IA standard"
    },
    "tpl-scene-occupancy": {
        "partial_status": "partial_aggregate",
        "partial_reason_fr": "Taux d'occupation de zone : agrégat scene_occupancy pas encore émis par l'IA standard"
    },
}

catalog_dir = Path("shared/rule-catalog")
total_tagged = 0
total_already = 0

for catalog_file in sorted(catalog_dir.glob("*.json")):
    with open(catalog_file, encoding="utf-8") as fh:
        data = json.load(fh)

    if isinstance(data, list):
        items = data
        root_is_list = True
    else:
        items = data.get("templates", [])
        root_is_list = False

    modified = False
    for tpl in items:
        if not isinstance(tpl, dict):
            continue
        tid = tpl.get("id", "")
        if tid in PARTIAL_TAGS:
            tag = PARTIAL_TAGS[tid]
            if tpl.get("partial_status") == tag["partial_status"] and tpl.get("partial_reason_fr") == tag["partial_reason_fr"]:
                total_already += 1
                continue
            tpl["partial_status"] = tag["partial_status"]
            tpl["partial_reason_fr"] = tag["partial_reason_fr"]
            modified = True
            total_tagged += 1
            print(f"  ✓ {tid} → {tag['partial_status']}")
        elif "partial_status" not in tpl:
            # Marquer explicitement "full" pour les templates complets
            tpl["partial_status"] = "full"
            modified = True

    if modified:
        if root_is_list:
            out = data
        else:
            out = data
        with open(catalog_file, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"Saved {catalog_file}")

print(f"\nDone: {total_tagged} newly tagged, {total_already} already correct")
