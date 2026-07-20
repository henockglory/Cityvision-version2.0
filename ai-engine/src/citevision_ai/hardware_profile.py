"""
CitéVision v2 — Hardware Profile & GPU Elasticity
Détecte automatiquement le tier GPU au démarrage et override
les paramètres de performance dans Settings avant toute initialisation.

Appeler hardware_profile.apply() dans main.py AVANT d'utiliser settings.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ─── Tier definitions ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class TierConfig:
    tier: str
    label: str
    yolo_model: str
    yolo_device: str
    max_cameras: int
    batch_size: int
    target_fps: float
    min_vram_mb: int


TIERS: list[TierConfig] = [
    TierConfig(
        tier="max",
        label="Max (RTX 4090/5090 16+ Go)",
        yolo_model="yolov8l.onnx",
        yolo_device="cuda",
        max_cameras=48,
        batch_size=32,
        target_fps=30.0,
        min_vram_mb=16000,
    ),
    TierConfig(
        tier="ultra",
        label="Ultra (RTX 4070–5060 8-16 Go)",
        yolo_model="yolov8m.onnx",
        yolo_device="cuda",
        max_cameras=24,
        batch_size=16,
        target_fps=25.0,
        min_vram_mb=8000,
    ),
    TierConfig(
        tier="high",
        label="High (RTX 3060–4060 6-12 Go)",
        yolo_model="yolov8s.onnx",
        yolo_device="cuda",
        max_cameras=16,
        batch_size=8,
        target_fps=15.0,
        min_vram_mb=5500,
    ),
    TierConfig(
        tier="standard",
        label="Standard (GTX 1060–2080 4-8 Go)",
        yolo_model="yolov8n.onnx",
        yolo_device="cuda",
        max_cameras=8,
        batch_size=4,
        target_fps=10.0,
        min_vram_mb=3000,
    ),
    TierConfig(
        tier="cpu-only",
        label="CPU-only (pas de GPU CUDA)",
        yolo_model="yolov8n.onnx",
        yolo_device="cpu",
        max_cameras=2,
        batch_size=1,
        target_fps=3.0,
        min_vram_mb=0,
    ),
]

_CPU_ONLY = TIERS[-1]


# ─── GPU Detection ─────────────────────────────────────────────────────────────
def _run(cmd: list[str], timeout: int = 8) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def detect_gpu_vram_mb() -> float:
    """
    Interroge nvidia-smi pour obtenir la VRAM totale en MiB.
    Retourne 0 si pas de GPU CUDA disponible.
    """
    out = _run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"])
    if not out:
        return 0.0
    # Prendre le GPU avec la plus grande VRAM
    vrams = []
    for line in out.splitlines():
        line = line.strip()
        if line.replace(".", "").isdigit():
            vrams.append(float(line))
    return max(vrams) if vrams else 0.0


def detect_cuda_version() -> tuple[int, int] | None:
    """Retourne (major, minor) de la version CUDA détectée, ou None."""
    # Via nvidia-smi
    out = _run(["nvidia-smi", "--query-gpu=driver_version,compute_cap",
                "--format=csv,noheader"])
    if out:
        for line in out.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                m = re.match(r"(\d+)\.(\d+)", parts[-1])
                if m:
                    return int(m.group(1)), int(m.group(2))
    # Via nvcc
    out2 = _run(["nvcc", "--version"])
    m = re.search(r"release (\d+)\.(\d+)", out2)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def classify_tier(vram_mb: float) -> TierConfig:
    for t in TIERS:
        if vram_mb >= t.min_vram_mb and t.min_vram_mb > 0:
            return t
    return _CPU_ONLY


# ─── Model availability check ──────────────────────────────────────────────────
def _model_exists(model_filename: str) -> bool:
    from pathlib import Path
    ai_root = Path(__file__).resolve().parents[2]
    return (ai_root / "models" / model_filename).exists()


def _best_available_model(desired: str) -> str:
    """
    Si le modèle souhaité n'existe pas, descend jusqu'au premier disponible.
    Ordre : yolov8l > yolov8m > yolov8s > yolov8n
    """
    order = ["yolov8l.onnx", "yolov8m.onnx", "yolov8s.onnx", "yolov8n.onnx"]
    # Try from desired downward
    start = order.index(desired) if desired in order else len(order) - 1
    for model in order[start:]:
        if _model_exists(model):
            return model
    # Fallback: any .onnx in models/
    from pathlib import Path
    ai_root = Path(__file__).resolve().parents[2]
    models = list((ai_root / "models").glob("*.onnx")) if (ai_root / "models").exists() else []
    return models[0].name if models else "yolov8n.onnx"


# ─── Main apply function ───────────────────────────────────────────────────────
def apply(settings=None) -> TierConfig:
    """
    Détecte le tier GPU et override les settings en place.
    Doit être appelé AVANT toute initialisation du pipeline.

    Returns the active TierConfig so callers can log/inspect it.
    """
    # Allow override via env var for CI / test
    forced_tier = os.environ.get("CITEVISION_GPU_TIER", "").lower()
    if forced_tier:
        tier = next((t for t in TIERS if t.tier == forced_tier), None)
        if tier:
            logger.info("[HWProfile] Tier forcé via env: %s", tier.label)
            if settings is not None:
                _apply_to_settings(settings, tier)
            return tier

    vram_mb = detect_gpu_vram_mb()
    tier = classify_tier(vram_mb)

    if vram_mb > 0:
        logger.info("[HWProfile] GPU détecté — VRAM: %.0f MiB → Tier: %s", vram_mb, tier.label)
    else:
        logger.info("[HWProfile] Aucun GPU CUDA détecté → Tier: CPU-only")

    # Ensure the requested YOLO model exists; downgrade if needed
    available_model = _best_available_model(tier.yolo_model)
    if available_model != tier.yolo_model:
        logger.warning(
            "[HWProfile] Modèle %s introuvable — utilisation de %s",
            tier.yolo_model, available_model,
        )
        # Create a patched tier with available model
        tier = TierConfig(
            tier=tier.tier, label=tier.label,
            yolo_model=available_model, yolo_device=tier.yolo_device,
            max_cameras=tier.max_cameras, batch_size=tier.batch_size,
            target_fps=tier.target_fps, min_vram_mb=tier.min_vram_mb,
        )

    if settings is not None:
        _apply_to_settings(settings, tier)

    return tier


def _apply_to_settings(settings, tier: TierConfig) -> None:
    """Override settings attributes based on detected tier."""
    # Only override if the setting is still at its default ("auto") or unset
    if getattr(settings, "hardware_tier", "auto") == "auto":
        settings.hardware_tier = tier.tier

    # Override YOLO config
    settings.yolo_model_path = f"models/{tier.yolo_model}"
    settings.yolo_device = tier.yolo_device
    settings.max_cameras = tier.max_cameras

    # Override batch_size if the attribute exists
    if hasattr(settings, "batch_size"):
        settings.batch_size = tier.batch_size

    # Override min FPS if attribute exists and device is CPU
    if hasattr(settings, "yolo_min_fps") and tier.yolo_device == "cpu":
        settings.yolo_min_fps = max(tier.target_fps, settings.yolo_min_fps * 0.3)

    logger.info(
        "[HWProfile] Settings appliqués — modèle=%s device=%s max_cameras=%d batch=%d",
        settings.yolo_model_path, settings.yolo_device,
        settings.max_cameras, tier.batch_size,
    )


def get_profile_info() -> dict:
    """Retourne un dict JSON-serializable avec le profil hardware courant."""
    vram_mb = detect_gpu_vram_mb()
    tier = classify_tier(vram_mb)
    cuda_ver = detect_cuda_version()
    return {
        "tier": tier.tier,
        "label": tier.label,
        "vram_mb": vram_mb,
        "cuda_version": f"{cuda_ver[0]}.{cuda_ver[1]}" if cuda_ver else None,
        "yolo_model": tier.yolo_model,
        "yolo_device": tier.yolo_device,
        "max_cameras": tier.max_cameras,
        "batch_size": tier.batch_size,
        "target_fps": tier.target_fps,
    }
