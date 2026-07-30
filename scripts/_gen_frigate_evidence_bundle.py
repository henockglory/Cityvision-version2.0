#!/usr/bin/env python3
"""Generate docs/FRIGATE-EVIDENCE-PIPELINE-BUNDLE.md from repo sources + live logs."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "FRIGATE-EVIDENCE-PIPELINE-BUNDLE.md"


def fence(lang: str, text: str) -> str:
    return f"```{lang}\n{text.rstrip()}\n```\n"


def section_file(title: str, rel: str, lang: str | None = None) -> str:
    p = ROOT / rel
    if not p.exists():
        return f"### {title}\n\n**MISSING:** `{rel}`\n\n"
    raw = p.read_text(encoding="utf-8", errors="replace")
    if lang is None:
        lang = {
            ".py": "python",
            ".go": "go",
            ".sql": "sql",
            ".md": "markdown",
            ".json": "json",
        }.get(p.suffix, "text")
    lines = raw.count("\n") + (0 if raw.endswith("\n") or not raw else 1)
    return (
        f"### {title}\n\n"
        f"- Path: `{rel}`\n"
        f"- Lines: {lines}\n\n"
        f"{fence(lang, raw)}\n"
    )


def try_live_logs() -> str:
    chunks: list[str] = []
    # Prefer WSL runtime log if present
    candidates = [
        Path.home() / "citevision-v2" / "logs" / "ai-engine.log",
        Path("/home/gheno/citevision-v2/logs/ai-engine.log"),
        ROOT / "logs" / "ai-engine.log",
    ]
    log_path = next((p for p in candidates if p.exists()), None)
    if log_path is None:
        chunks.append(
            "_Aucun `ai-engine.log` trouvé (WSL `~/citevision-v2/logs` ou repo `logs/`)._\n"
        )
    else:
        chunks.append(f"- Source log: `{log_path}`\n\n")
        try:
            # binary-safe grep for relevant lines
            raw = log_path.read_bytes()
            text = raw.decode("utf-8", errors="replace")
            keys = (
                "align_delta",
                "frigate_event_id",
                "frigate_bind",
                "soft-accept",
                "demo vehicle fallback",
                "ignore stale bind",
                "bound capture",
                "reject IoU",
                "demo_loop_guard",
                "road IA bbox",
                "Frigate bbox on scene",
                "no correlated event",
                "speeding",
                "red_light",
            )
            lines = [
                ln
                for ln in text.splitlines()
                if any(k in ln for k in keys)
            ]
            recent = lines[-80:] if lines else []
            chunks.append(f"Lignes filtrées (dernières {len(recent)} / {len(lines)} match):\n\n")
            chunks.append(fence("text", "\n".join(recent) if recent else "(aucune ligne match)"))
        except OSError as exc:
            chunks.append(f"_Lecture log échouée: {exc}_\n")

    # DB/API audit if script exists
    audit = ROOT / "scripts" / "_tmp_audit_evidence_provenance.py"
    if audit.exists():
        chunks.append("\n### Audit provenance alertes (script)\n\n")
        try:
            proc = subprocess.run(
                ["python3", str(audit)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=60,
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            chunks.append(fence("text", out[-12000:] if out else f"exit={proc.returncode} empty"))
        except Exception as exc:  # noqa: BLE001
            chunks.append(f"_Audit non exécutable ici: {exc}_\n")
    else:
        chunks.append("\n_Script `scripts/_tmp_audit_evidence_provenance.py` absent._\n")

    # Grep bound_at if present anywhere in recent lines
    chunks.append(
        "\n### Note sur `bound_at`\n\n"
        "`bound_at` est un champ **in-memory** du dataclass `FrigateTrackBinding` "
        "(binder). Il n’est **pas** persisté dans `evidence_snapshot` aujourd’hui. "
        "Pour calibrer `max_age_sec`, ajouter un log "
        "`frigate_bind ... age=%.2fs` à l’inject, ou écrire "
        "`metadata.frigate_bind_age_sec` au moment de l’émission.\n"
    )
    return "".join(chunks)


def main() -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    parts: list[str] = []
    parts.append(
        f"""# Bundle pipeline Frigate / preuves CitéVision

> Généré le {now}  
> Workspace: `C:\\\\Users\\\\gheno\\\\citevision`  
> Runtime de vérité: WSL `~/citevision-v2` (launcher `Start-CiteVision.ps1`)

Ce document regroupe le code, la config, le schéma et les tests demandés pour
préparer le correctif binder + alignement temporel démo (feu / vitesse).

## Table des matières

1. [Cœur détection / preuve](#1-cœur-du-pipeline-détectionpreuve)
2. [Alignement temporel démo](#2-alignement-temporel-démo)
3. [Modules métier](#3-modules-métier-spécifiques)
4. [Backend Frigate Go](#4-intégration-frigate-côté-backend-go)
5. [Modèle de données](#5-modèle-de-données)
6. [Tests existants](#6-tests-existants)
7. [Logs / données réelles](#7-logsdonnées-réelles-récentes)
8. [Carte des responsabilités](#8-carte-des-responsabilités-rappel-correctif)

---

## Notes importantes avant lecture

| Fait | Détail |
|------|--------|
| `_bound_usable_for_road` | **N’existe pas encore** — à créer dans le correctif |
| `aligned_anchor` / `learn_clock_offset` / `_demo_clock_offset` | `frigate_timeline.py` + état sur `FrigateTrackEvidence` — **pas** dans le binder |
| `match_track_to_event` / `_maybe_learn_offset` | Sur `FrigateTrackEvidence` |
| Soft keys `frigate_red_light_soft_iou` / `frigate_speed_soft_iou` | Métadonnées runtime event — **pas** des settings |
| Skip inject feu/vitesse | `pipeline.py` ~L1009-1013 **et** ignore bound dans `_capture_impl` |

---

"""
    )

    parts.append("## 1. Cœur du pipeline détection/preuve\n\n")
    parts.append(
        section_file(
            "1.1 `pipeline.py` (fichier complet)",
            "ai-engine/src/citevision_ai/pipeline.py",
            "python",
        )
    )
    parts.append(
        section_file(
            "1.2 `frigate_track_evidence.py` (fichier complet)",
            "ai-engine/src/citevision_ai/evidence/frigate_track_evidence.py",
            "python",
        )
    )
    parts.append(
        section_file(
            "1.3 `frigate_track_binder.py` (fichier complet)",
            "ai-engine/src/citevision_ai/evidence/frigate_track_binder.py",
            "python",
        )
    )
    parts.append(
        section_file(
            "1.4 `evidence/service.py` (wrappers update/inject)",
            "ai-engine/src/citevision_ai/evidence/service.py",
            "python",
        )
    )
    parts.append(
        """### 1.5 Clarification API (où est quoi)

| Symbole | Fichier réel |
|---------|--------------|
| `update_frigate_bindings` | `evidence/service.py` → `FrigateTrackBinder.update_tracks` |
| `inject_frigate_binding` | `evidence/service.py` → `FrigateTrackBinder.inject_event` |
| `match_track_to_event` | `frigate_track_evidence.py` |
| `_demo_clock_offset` | instance `FrigateTrackEvidence` |
| `_maybe_learn_offset` | `frigate_track_evidence.py` |
| `aligned_anchor` / `learn_clock_offset` | `frigate_timeline.py` |
| `_demo_latest_vehicle_event` | `frigate_track_evidence.py` |
| `_bound_usable_for_road` | **absent** (à créer) |

Extraits critiques `pipeline.py` (émission):

```python
# ~891-894 : maj bindings tous tracks
self.evidence.update_frigate_bindings(
    camera_id, track_dicts, frame_w=w, frame_h=h, wall_ts=frame_wall_ts,
)

# ~1009-1013 : inject SAUF red_light / speeding
if str(evt.get("event_type") or "") not in ("red_light_violation", "speeding"):
    self.evidence.inject_frigate_binding(camera_id, evt)
```

---
"""
    )

    parts.append("## 2. Alignement temporel démo\n\n")
    parts.append(
        section_file(
            "2.1 `frigate_timeline.py` (fichier complet)",
            "ai-engine/src/citevision_ai/evidence/frigate_timeline.py",
            "python",
        )
    )
    parts.append(
        section_file(
            "2.2 `config.py` (fichier complet — settings IA)",
            "ai-engine/src/citevision_ai/config.py",
            "python",
        )
    )
    parts.append(
        """### 2.3 Table des settings Frigate / démo (valeurs défaut actuelles)

| Setting | Défaut | Rôle |
|---------|--------|------|
| `demo_mode` | False (+ resolve env) | Active soft-accept / paths démo |
| `demo_evidence_backend` | `strict_frigate` | Backend preuves démo |
| `demo_red_light_loop_sec` | 352.52 | Durée boucle Feux |
| `demo_loop_guard` | True | Gate abs + même cycle boucle |
| `frigate_demo_timeline_align` | True | Offset horloge démo |
| `frigate_demo_max_align_sec` | 10.0 | Max \\|IA−Frigate\\| correlate |
| `frigate_demo_accept_max_align_sec` | 30.0 | Max accept (red_light clampé plus bas) |
| `frigate_demo_min_bbox_iou` | 0.12 | IoU min démo pick |
| `frigate_accept_min_bbox_iou` | 0.15 | IoU min accept evidence |
| `frigate_bind_min_iou` | 0.12 | IoU min binder |
| `frigate_bind_every_n_frames` | 2 | Fréquence maj binder |
| `frigate_track_binding_enabled` | True | Master binder |
| `frigate_correlate_wait_sec` | 12.0 | Poll correlate |
| `frigate_red_light_soft_iou` | — | **Pas un setting** : clé meta event |
| `frigate_speed_soft_iou` | — | **Pas un setting** : clé meta event |

---
"""
    )

    parts.append("## 3. Modules métier spécifiques\n\n")
    parts.append(
        section_file(
            "3.1 `zone_speed.py` (fichier complet)",
            "ai-engine/src/citevision_ai/analytics/zone_speed.py",
            "python",
        )
    )
    parts.append(
        section_file(
            "3.2 `traffic_light.py` (fichier complet)",
            "ai-engine/src/citevision_ai/road_enforcement/traffic_light.py",
            "python",
        )
    )

    parts.append("## 4. Intégration Frigate côté backend Go\n\n")
    parts.append(
        section_file(
            "4.1 `compiler.go` (fichier complet)",
            "backend/internal/frigate/compiler.go",
            "go",
        )
    )
    parts.append(
        section_file(
            "4.2 `FRIGATE-INTEGRATION.md` (fichier complet)",
            "docs/FRIGATE-INTEGRATION.md",
            "markdown",
        )
    )

    parts.append("## 5. Modèle de données\n\n")
    models_path = ROOT / "backend/internal/models/models.go"
    models = models_path.read_text(encoding="utf-8", errors="replace")
    start = models.find("type Zone struct")
    end = models.find("type Incident struct")
    parts.append("### 5.1 ORM Go — Zone / Line / Event / Rule / Alert\n\n")
    if start >= 0 and end > start:
        parts.append(fence("go", models[start:end]))
    else:
        parts.append(fence("go", models))

    for rel, title in [
        ("backend/migrations/000006_zones_lines.up.sql", "5.2 Migration zones/lines"),
        ("backend/migrations/000007_events_rules.up.sql", "5.3 Migration events/rules"),
        ("backend/migrations/000016_zone_kind.up.sql", "5.4 Migration zone_kind"),
        ("backend/migrations/000019_zone_behaviors.up.sql", "5.5 Migration behavior_config zones"),
        ("backend/migrations/000020_line_counters.up.sql", "5.6 Migration line_counters"),
        ("backend/migrations/000021_line_behaviors.up.sql", "5.7 Migration behavior_config lines"),
    ]:
        parts.append(section_file(title, rel, "sql"))

    caps = ROOT / "shared/ai-capabilities.json"
    if caps.exists():
        data = json.loads(caps.read_text(encoding="utf-8"))
        templates = data.get("templates", {})
        picks = {
            tid: templates[tid]
            for tid in [
                "tpl-speeding-premium",
                "tpl-red-light",
                "tpl-phone-driving",
                "tpl-seatbelt",
                "tpl-line-cross",
                "tpl-scene-occupancy",
                "tpl-vandalism",
            ]
            if tid in templates
        }
        supported = sum(1 for t in templates.values() if t.get("supported") is True)
        unsupported = sum(1 for t in templates.values() if t.get("supported") is False)
        parts.append("### 5.8 Extrait représentatif `shared/ai-capabilities.json`\n\n")
        parts.append(f"- Templates totaux: {len(templates)}\n")
        parts.append(f"- `supported: true`: {supported}\n")
        parts.append(f"- `supported: false`: {unsupported}\n\n")
        parts.append(
            fence("json", json.dumps({"templates_sample": picks}, indent=2, ensure_ascii=False))
        )

    parts.append("\n---\n\n## 6. Tests existants\n\n")
    parts.append(
        section_file(
            "6.1 `test_demo_loop_guard.py`",
            "ai-engine/tests/test_demo_loop_guard.py",
            "python",
        )
    )
    parts.append(
        section_file(
            "6.2 `test_frigate_track_binder.py`",
            "ai-engine/tests/test_frigate_track_binder.py",
            "python",
        )
    )
    parts.append(
        """### 6.3 Couverture actuelle vs correctif proposé

| Scénario | Couvert ? |
|----------|-----------|
| Reject delta 720s sous demo_loop_guard | Oui |
| Accept delta serré | Oui |
| Soft red ne élargit pas la fenêtre | Oui |
| inject_event pose frigate_event_id | Oui |
| update_tracks skip si disabled | Oui |
| update_tracks réserve sur IoU | Oui |
| Bound frais + IoU OK pour speeding | **Non** (à ajouter) |
| Bound vieux (>max_age) → re-correlate | **Non** |
| IoU 0 → missing (pas soft) | **Non** |
| ignore_time_filter=False en démo | **Non** |

---
"""
    )

    parts.append("## 7. Logs/données réelles récentes\n\n")
    parts.append(try_live_logs())

    parts.append(
        """
---

## 8. Carte des responsabilités (rappel correctif)

```
pipeline.py
  update_frigate_bindings()  --> FrigateTrackBinder.update_tracks()
       |                              |
       |                              v
       |                     FrigateTrackEvidence.match_track_to_event()
       |                              |  (today: ignore_time_filter=True)
       |                              v
       |                     learn_clock_offset / _demo_clock_offset
       |
       v
  emit event (bbox_ts, track_id, bbox IA)
       |
       +-- inject_frigate_binding  [SKIP red_light/speeding today]
       |
       v
  FrigateTrackEvidence.capture / _capture_impl
       |
       +-- ignore bound_id for red_light/speeding  [today]
       +-- _correlate_event (+ timeline align)
       +-- soft-accept IoU / demo vehicle fallback  [remove for honesty]
       +-- _compose_from_matched --> evidence package
```

Correctif cible (résumé):

1. Durcir binder (temps + loop cycle + IoU)
2. Réinjecter bind feu/vitesse si frais (`max_age_sec` à calibrer via logs §7)
3. Trust bound road seulement si `_bound_usable_for_road` (à créer)
4. Couper soft-accept + `_demo_latest_vehicle_event` pour road rules

---

*Fin du bundle.*
"""
    )

    text = "".join(parts)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT} bytes={OUT.stat().st_size} lines={text.count(chr(10)) + 1}")


if __name__ == "__main__":
    main()
