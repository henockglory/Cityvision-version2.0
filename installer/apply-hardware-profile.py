#!/usr/bin/env python3
"""
CitéVision v2 — Hardware Profile Applicator
Détecte le tier GPU via check-hardware.py et génère generated.env
dans le répertoire racine du projet.

Usage:
    python installer/apply-hardware-profile.py [--dry-run] [--output=<path>]

Options:
    --dry-run       Affiche le profil sans écrire le fichier
    --output=<path> Chemin de sortie (défaut: <ROOT>/generated.env)
    --json          Sortie JSON uniquement (pour intégration setup-server.py)
"""
from __future__ import annotations

import importlib.util
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime

IS_WINDOWS = platform.system() == "Windows"
INSTALLER_DIR = Path(__file__).resolve().parent
ROOT = INSTALLER_DIR.parent
DEFAULT_OUTPUT = ROOT / "generated.env"

# Mapping tier → env vars
TIER_ENV_MAP = {
    "max": {
        "CV_GPU_TIER": "max",
        "CV_MAX_CAMERAS": "48",
        "CV_YOLO_MODEL": "yolov8l.onnx",
        "CV_BATCH_SIZE": "32",
        "CV_TARGET_FPS": "30",
        "CV_INFERENCE_BACKEND": "cuda",
        "MAX_CAMERAS": "48",
        "YOLO_MODEL_PATH": "models/yolov8l.onnx",
    },
    "ultra": {
        "CV_GPU_TIER": "ultra",
        "CV_MAX_CAMERAS": "24",
        "CV_YOLO_MODEL": "yolov8m.onnx",
        "CV_BATCH_SIZE": "16",
        "CV_TARGET_FPS": "25",
        "CV_INFERENCE_BACKEND": "cuda",
        "MAX_CAMERAS": "24",
        "YOLO_MODEL_PATH": "models/yolov8m.onnx",
    },
    "high": {
        "CV_GPU_TIER": "high",
        "CV_MAX_CAMERAS": "16",
        "CV_YOLO_MODEL": "yolov8s.onnx",
        "CV_BATCH_SIZE": "8",
        "CV_TARGET_FPS": "15",
        "CV_INFERENCE_BACKEND": "cuda",
        "MAX_CAMERAS": "16",
        "YOLO_MODEL_PATH": "models/yolov8s.onnx",
    },
    "standard": {
        "CV_GPU_TIER": "standard",
        "CV_MAX_CAMERAS": "8",
        "CV_YOLO_MODEL": "yolov8n.onnx",
        "CV_BATCH_SIZE": "4",
        "CV_TARGET_FPS": "10",
        "CV_INFERENCE_BACKEND": "cuda",
        "MAX_CAMERAS": "8",
        "YOLO_MODEL_PATH": "models/yolov8n.onnx",
    },
    "cpu-only": {
        "CV_GPU_TIER": "cpu-only",
        "CV_MAX_CAMERAS": "2",
        "CV_YOLO_MODEL": "yolov8n.onnx",
        "CV_BATCH_SIZE": "1",
        "CV_TARGET_FPS": "3",
        "CV_INFERENCE_BACKEND": "cpu",
        "MAX_CAMERAS": "2",
        "YOLO_MODEL_PATH": "models/yolov8n.onnx",
    },
}


def _run_subprocess(cmd: list[str], timeout: int = 20) -> tuple[int, str, str]:
    """Exécute une commande sans fenêtre (Windows-safe)."""
    kwargs: dict = dict(
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    kwargs["env"] = env
    try:
        r = subprocess.run(cmd, **kwargs)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def detect_gpu_tier_via_check_hardware() -> dict:
    """
    Appelle check-hardware.py pour obtenir le gpu_tier.
    Retourne le dict gpu_tier ou un fallback cpu-only.
    """
    hw_script = INSTALLER_DIR / "check-hardware.py"
    if not hw_script.exists():
        return {"tier": "cpu-only", "label": "CPU-only (check-hardware.py introuvable)",
                "max_cameras": 2, "yolo_model": "yolov8n.onnx",
                "batch_size": 1, "target_fps": 3}

    code, out, err = _run_subprocess([sys.executable, str(hw_script)], timeout=30)
    if code == 0 and out.strip():
        try:
            data = json.loads(out)
            tier = data.get("gpu_tier", {})
            if tier and tier.get("tier"):
                return tier
        except json.JSONDecodeError:
            pass

    # Fallback: détection directe via nvidia-smi
    return _direct_gpu_detect()


def _direct_gpu_detect() -> dict:
    """Détection GPU directe via nvidia-smi sans passer par check-hardware.py."""
    code, out, _ = _run_subprocess(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
        timeout=10
    )
    if code != 0 or not out.strip():
        return {"tier": "cpu-only", "label": "CPU-only (pas de GPU NVIDIA)",
                "max_cameras": 2, "yolo_model": "yolov8n.onnx",
                "batch_size": 1, "target_fps": 3}

    lines = out.strip().splitlines()
    best_vram = 0.0
    best_name = "GPU inconnu"
    for line in lines:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            try:
                vram = float(parts[1])
                if vram > best_vram:
                    best_vram = vram
                    best_name = parts[0]
            except ValueError:
                pass

    if best_vram >= 16000:
        return {"tier": "max", "label": f"Max ({best_name})",
                "max_cameras": 48, "yolo_model": "yolov8l.onnx",
                "batch_size": 32, "target_fps": 30}
    if best_vram >= 8000:
        return {"tier": "ultra", "label": f"Ultra ({best_name})",
                "max_cameras": 24, "yolo_model": "yolov8m.onnx",
                "batch_size": 16, "target_fps": 25}
    if best_vram >= 6000:
        return {"tier": "high", "label": f"High ({best_name})",
                "max_cameras": 16, "yolo_model": "yolov8s.onnx",
                "batch_size": 8, "target_fps": 15}
    if best_vram >= 3000:
        return {"tier": "standard", "label": f"Standard ({best_name})",
                "max_cameras": 8, "yolo_model": "yolov8n.onnx",
                "batch_size": 4, "target_fps": 10}
    return {"tier": "cpu-only", "label": f"CPU-only (VRAM {best_vram:.0f} MiB insuffisante)",
            "max_cameras": 2, "yolo_model": "yolov8n.onnx",
            "batch_size": 1, "target_fps": 3}


def _best_available_model(desired: str) -> str:
    """Descend vers un modèle disponible si le modèle désiré est absent."""
    order = ["yolov8l.onnx", "yolov8m.onnx", "yolov8s.onnx", "yolov8n.onnx"]
    models_dir = ROOT / "ai-engine" / "models"
    start = order.index(desired) if desired in order else len(order) - 1
    for model in order[start:]:
        if (models_dir / model).exists():
            return model
    # Aucun modèle trouvé — conserver le désiré (sera téléchargé)
    return desired


def build_env_content(tier_info: dict) -> str:
    """Construit le contenu du fichier generated.env."""
    tier_key = tier_info.get("tier", "cpu-only")
    if tier_key not in TIER_ENV_MAP:
        tier_key = "cpu-only"

    env_vars = dict(TIER_ENV_MAP[tier_key])

    # Ajuster le modèle selon ce qui est disponible
    desired_model = env_vars.get("CV_YOLO_MODEL", "yolov8n.onnx")
    available_model = _best_available_model(desired_model)
    if available_model != desired_model:
        env_vars["CV_YOLO_MODEL"] = available_model
        env_vars["YOLO_MODEL_PATH"] = f"models/{available_model}"

    # Enrichir avec infos du tier
    env_vars["CV_GPU_LABEL"] = tier_info.get("label", tier_key)
    vram = tier_info.get("vram_mb", 0)
    if vram:
        env_vars["CV_GPU_VRAM_MB"] = str(int(vram))
    cuda_ver = tier_info.get("cuda_version")
    if cuda_ver:
        env_vars["CV_CUDA_VERSION"] = str(cuda_ver)

    lines = [
        "# ═══════════════════════════════════════════════════════════════════",
        "# CitéVision v2 — Hardware Profile (auto-généré par apply-hardware-profile.py)",
        f"# Généré le: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"# Tier détecté: {env_vars.get('CV_GPU_TIER', 'unknown')} — {env_vars.get('CV_GPU_LABEL', '')}",
        "# NE PAS ÉDITER MANUELLEMENT — relancez apply-hardware-profile.py",
        "# ═══════════════════════════════════════════════════════════════════",
        "",
    ]

    sections = {
        "GPU Tier": ["CV_GPU_TIER", "CV_GPU_LABEL", "CV_GPU_VRAM_MB", "CV_CUDA_VERSION"],
        "Performance": ["CV_MAX_CAMERAS", "CV_YOLO_MODEL", "CV_BATCH_SIZE",
                        "CV_TARGET_FPS", "CV_INFERENCE_BACKEND"],
        "AI Engine (compatibilité)": ["MAX_CAMERAS", "YOLO_MODEL_PATH"],
    }

    for section, keys in sections.items():
        lines.append(f"# --- {section} ---")
        for key in keys:
            if key in env_vars:
                lines.append(f"{key}={env_vars[key]}")
        lines.append("")

    return "\n".join(lines)


def apply(output_path: Path | None = None, dry_run: bool = False, json_output: bool = False) -> dict:
    """
    Point d'entrée principal.
    1. Détecte le tier GPU
    2. Génère generated.env
    3. Retourne le profil sous forme de dict
    """
    tier_info = detect_gpu_tier_via_check_hardware()
    tier_key = tier_info.get("tier", "cpu-only")

    env_vars_map = dict(TIER_ENV_MAP.get(tier_key, TIER_ENV_MAP["cpu-only"]))
    desired_model = env_vars_map.get("CV_YOLO_MODEL", "yolov8n.onnx")
    available_model = _best_available_model(desired_model)
    if available_model != desired_model:
        env_vars_map["CV_YOLO_MODEL"] = available_model
        env_vars_map["YOLO_MODEL_PATH"] = f"models/{available_model}"

    result = {
        "tier": tier_key,
        "label": tier_info.get("label", tier_key),
        "yolo_model": env_vars_map.get("CV_YOLO_MODEL", "yolov8n.onnx"),
        "max_cameras": int(env_vars_map.get("CV_MAX_CAMERAS", 2)),
        "batch_size": int(env_vars_map.get("CV_BATCH_SIZE", 1)),
        "target_fps": int(env_vars_map.get("CV_TARGET_FPS", 3)),
        "inference_backend": env_vars_map.get("CV_INFERENCE_BACKEND", "cpu"),
        "generated_env": str(output_path or DEFAULT_OUTPUT),
        "dry_run": dry_run,
    }

    if not dry_run:
        out_path = output_path or DEFAULT_OUTPUT
        content = build_env_content(tier_info)
        out_path.write_text(content, encoding="utf-8")
        result["written"] = True
    else:
        result["written"] = False
        result["env_preview"] = build_env_content(tier_info)

    return result


def main() -> int:
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    json_out = "--json" in args

    output_path = DEFAULT_OUTPUT
    for arg in args:
        if arg.startswith("--output="):
            output_path = Path(arg.split("=", 1)[1])

    try:
        result = apply(output_path=output_path, dry_run=dry_run, json_output=json_out)

        if json_out:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            tier = result["tier"]
            label = result["label"]
            print(f"[HW-Profile] Tier détecté: {tier} — {label}")
            print(f"[HW-Profile] Modèle YOLO : {result['yolo_model']}")
            print(f"[HW-Profile] Caméras max : {result['max_cameras']}")
            print(f"[HW-Profile] Batch size  : {result['batch_size']}")
            print(f"[HW-Profile] FPS cible   : {result['target_fps']}")
            print(f"[HW-Profile] Backend      : {result['inference_backend']}")
            if dry_run:
                print("[HW-Profile] Mode dry-run — generated.env non écrit")
                print("\nContenu qui serait généré:")
                print(result.get("env_preview", ""))
            else:
                print(f"[HW-Profile] Fichier généré: {result['generated_env']}")
        return 0

    except Exception as e:
        import traceback
        if json_out:
            print(json.dumps({"error": str(e), "traceback": traceback.format_exc()},
                             ensure_ascii=False))
        else:
            print(f"[HW-Profile] ERREUR: {e}", file=sys.stderr)
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
