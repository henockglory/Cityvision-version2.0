"""
CitéVision v2 — Auto-fix orchestrator for installer SSE streams.
Linux native + Windows (via WSL bash).
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parent.parent
IS_WINDOWS = platform.system() == "Windows"
MAX_ROUNDS = 8
AI_HEALTH_URL = "http://localhost:8001/health"

HEALTH_KEYS = ("yolo_loaded", "face_loaded", "plate_loaded")


def _to_wsl_path(win_path: Path) -> str:
    import re
    p = str(win_path)
    # Fast local conversion: C:\foo\bar → /mnt/c/foo/bar
    m = re.match(r"^([A-Za-z]):[/\\](.*)", p)
    if m:
        rest = m.group(2).replace("\\", "/")
        return f"/mnt/{m.group(1).lower()}/{rest}"
    return p.replace("\\", "/")


def _run_bash(script_rel: str, *args: str, timeout: int = 600) -> tuple[int, str]:
    script = ROOT / script_rel
    if IS_WINDOWS:
        wsl_script = _to_wsl_path(script)
        wsl_args = " ".join(f"'{a}'" for a in args)
        cmd = ["wsl", "--", "bash", wsl_script] + list(args)
    else:
        cmd = ["bash", str(script)] + list(args)
    try:
        r = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
        )
        out = (r.stdout or "") + (r.stderr or "")
        return r.returncode, out.strip()
    except subprocess.TimeoutExpired:
        return 1, f"Timeout ({timeout}s) sur {script_rel}"
    except Exception as e:
        return 1, str(e)


def fetch_ai_health(url: str = AI_HEALTH_URL) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def diagnose(health: dict | None) -> list[str]:
    missing: list[str] = []
    if health is None:
        missing.append("ai_down")
        return missing
    for key in HEALTH_KEYS:
        if str(health.get(key, "")).lower() != "true":
            missing.append(key)
    return missing


def _check_imports() -> bool:
    rc, _ = _run_bash("scripts/ensure-ai-stack.sh", "--verify-only", timeout=120)
    return rc == 0


def remediate_stream(missing: list[str]) -> Iterator[str]:
    """Yield log lines for each remediation action."""
    if "ai_down" in missing or not _check_imports():
        yield "Installation / réparation des dépendances Python (InsightFace + PaddleOCR)…"
        rc, out = _run_bash(
            "scripts/ensure-ai-stack.sh", "--fix", "--max-attempts=3", timeout=900
        )
        for line in out.splitlines()[-20:]:
            if line.strip():
                yield line.strip()
        if rc != 0:
            yield "Première passe ensure-ai-stack — nouvelle tentative…"

    if any(k in missing for k in HEALTH_KEYS) or "ai_down" in missing:
        yield "Téléchargement / initialisation des modèles IA…"
        rc, out = _run_bash("scripts/download-models.sh", "--skip-yolo", timeout=600)
        for line in out.splitlines()[-15:]:
            if line.strip():
                yield line.strip()

    if any(k in missing for k in HEALTH_KEYS) or "ai_down" in missing:
        yield "Redémarrage AI engine…"
        rc, out = _run_bash(
            "scripts/ensure-ai-stack.sh",
            "--fix", "--restart-ai",
            f"--health-url={AI_HEALTH_URL}",
            "--max-attempts=2",
            timeout=600,
        )
        for line in out.splitlines()[-15:]:
            if line.strip():
                yield line.strip()


def ensure_install_stack_stream(max_rounds: int = 5) -> Iterator[dict]:
    """Post-setup validation: imports + models (no running AI required)."""
    for rnd in range(1, max_rounds + 1):
        yield {"event": "fix", "message": f"Vérification AI stack post-install ({rnd}/{max_rounds})…"}
        rc, out = _run_bash(
            "scripts/ensure-ai-stack.sh",
            "--verify-only",
            "--health-url=none",
            timeout=180,
        )
        if rc == 0:
            yield {"event": "ok", "message": "AI stack validé (pip + modèles)"}
            return
        for line in out.splitlines():
            if "[ERR]" in line or "[FIX]" in line:
                yield {"event": "fix", "message": line.strip()}
        yield {"event": "fix", "message": "Correction AI stack post-install…"}
        rc, out = _run_bash(
            "scripts/ensure-ai-stack.sh", "--fix", "--max-attempts=3", timeout=3600
        )
        for line in out.splitlines():
            if "[FIX]" in line or "[OK]" in line or "[ERR]" in line:
                yield {"event": "fix", "message": line.strip()}
        if rc == 0:
            yield {"event": "ok", "message": "AI stack validé (pip + modèles)"}
            return
        time.sleep(3)
    yield {"event": "error", "message": "AI stack non validé après remédiation post-install"}


def ensure_launch_ai_stream(max_rounds: int = MAX_ROUNDS) -> Iterator[dict]:
    """Poll AI health and auto-fix until all models loaded or rounds exhausted."""
    for rnd in range(1, max_rounds + 1):
        health = fetch_ai_health()
        missing = diagnose(health)
        if not missing:
            yield {
                "event": "ai_ready",
                "message": "AI Engine opérationnel — YOLO, InsightFace et PaddleOCR chargés",
            }
            return

        labels = {
            "yolo_loaded": "YOLO",
            "face_loaded": "InsightFace",
            "plate_loaded": "PaddleOCR",
            "ai_down": "AI Engine",
        }
        miss_txt = ", ".join(labels.get(m, m) for m in missing)
        yield {
            "event": "fix",
            "message": f"Correction automatique IA ({rnd}/{max_rounds}) — manquant : {miss_txt}",
        }

        for line in remediate_stream(missing):
            yield {"event": "fix", "message": line}

        # Wait for models after fix
        deadline = time.time() + 90
        while time.time() < deadline:
            health = fetch_ai_health()
            if not diagnose(health):
                yield {
                    "event": "ai_ready",
                    "message": "AI Engine opérationnel — YOLO, InsightFace et PaddleOCR chargés",
                }
                return
            time.sleep(3)

    health = fetch_ai_health()
    missing = diagnose(health)
    labels = {
        "yolo_loaded": "YOLO",
        "face_loaded": "Reconnaissance faciale (InsightFace)",
        "plate_loaded": "Lecture de plaques (PaddleOCR)",
        "ai_down": "AI Engine non joignable",
    }
    miss_txt = ", ".join(labels.get(m, m) for m in missing) if missing else "inconnu"
    yield {
        "event": "ai_fail",
        "message": (
            f"Modèles IA incomplets après {max_rounds} rounds de correction : {miss_txt}. "
            "Consultez logs/ai-engine.log"
        ),
    }
