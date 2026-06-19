#!/usr/bin/env python3
"""
CitéVision v2 — Hardware Requirements Checker
Retourne un JSON structuré avec pass/warn/fail pour chaque critère.
Utilisé par le serveur d'installation (setup-server.py).
"""
from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

Status = Literal["pass", "warn", "fail"]

# ---------------------------------------------------------------------------
# Seuils
# ---------------------------------------------------------------------------
MINIMUM = {
    "cpu_threads": 8,
    "cpu_freq_ghz": 2.0,
    "ram_gb": 8,
    "disk_gb": 50,
    "gpu_vram_mb": 0,        # 0 = GPU optionnel (fallback CPU-only)
    "gpu_cuda_major": 11,
}
RECOMMENDED = {
    "cpu_threads": 16,
    "cpu_freq_ghz": 3.0,
    "ram_gb": 16,
    "disk_gb": 200,
    "gpu_vram_mb": 6000,
    "gpu_cuda_major": 12,
}
OPTIMAL = {
    "cpu_threads": 18,
    "cpu_freq_ghz": 3.5,
    "ram_gb": 28,
    "disk_gb": 500,
    "gpu_vram_mb": 6141,
    "gpu_cuda_major": 12,
    "gpu_driver": "566.36",
}


@dataclass
class Check:
    id: str
    label: str
    status: Status
    value: str
    expected: str
    detail: str = ""
    technical: str = ""


def _run(cmd: list[str], timeout: int = 5) -> str:
    try:
        kwargs: dict = dict(
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        # On Windows hidden-window processes, subprocesses must not inherit
        # the invalid console handles — otherwise they block indefinitely.
        if platform.system() == "Windows":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        r = subprocess.run(cmd, **kwargs)
        return r.stdout.strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# CPU
# ---------------------------------------------------------------------------
def check_cpu() -> list[Check]:
    checks: list[Check] = []
    info = platform.processor() or "inconnu"

    # Threads (logical CPUs)
    try:
        import os
        threads = os.cpu_count() or 1
    except Exception:
        threads = 1

    if threads >= RECOMMENDED["cpu_threads"]:
        status: Status = "pass"
        detail = "Excellent — traitement vidéo multi-flux optimal"
    elif threads >= MINIMUM["cpu_threads"]:
        status = "warn"
        detail = "Suffisant — performances correctes jusqu'à 8 caméras"
    else:
        status = "fail"
        detail = f"Insuffisant — minimum {MINIMUM['cpu_threads']} threads requis pour le pipeline IA"

    checks.append(Check(
        id="cpu_threads",
        label="CPU — Threads logiques",
        status=status,
        value=f"{threads} threads ({info})",
        expected=f"≥ {MINIMUM['cpu_threads']} (recommandé {RECOMMENDED['cpu_threads']}+)",
        detail=detail,
        technical=f"os.cpu_count() = {threads} | platform.processor() = {info}",
    ))

    # Fréquence via cpuinfo ou /proc/cpuinfo
    freq_ghz = _get_cpu_freq_ghz()
    if freq_ghz and freq_ghz >= RECOMMENDED["cpu_freq_ghz"]:
        freq_status: Status = "pass"
        freq_detail = "Fréquence optimale pour l'inférence YOLO temps-réel"
    elif freq_ghz and freq_ghz >= MINIMUM["cpu_freq_ghz"]:
        freq_status = "warn"
        freq_detail = "Fréquence acceptable — latence légèrement plus élevée"
    elif freq_ghz:
        freq_status = "fail"
        freq_detail = f"Fréquence trop basse — minimum {MINIMUM['cpu_freq_ghz']} GHz requis"
    else:
        freq_status = "warn"
        freq_detail = "Impossible de lire la fréquence — vérification manuelle recommandée"

    checks.append(Check(
        id="cpu_freq",
        label="CPU — Fréquence maximale",
        status=freq_status,
        value=f"{freq_ghz:.2f} GHz" if freq_ghz else "non détecté",
        expected=f"≥ {MINIMUM['cpu_freq_ghz']} GHz (recommandé {RECOMMENDED['cpu_freq_ghz']}+ GHz)",
        detail=freq_detail,
        technical="Source: /proc/cpuinfo ou cpufreq",
    ))

    return checks


def _get_cpu_freq_ghz() -> float | None:
    # Linux: /proc/cpuinfo
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if "cpu MHz" in line:
                    mhz = float(line.split(":")[1].strip())
                    return mhz / 1000.0
    except Exception:
        pass
    # Windows: wmic
    out = _run(["wmic", "cpu", "get", "MaxClockSpeed", "/value"])
    m = re.search(r"MaxClockSpeed=(\d+)", out)
    if m:
        return int(m.group(1)) / 1000.0
    return None


# ---------------------------------------------------------------------------
# RAM
# ---------------------------------------------------------------------------
def check_ram() -> Check:
    gb = 0.0
    # Linux
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    gb = int(line.split()[1]) / 1024 / 1024
                    break
    except Exception:
        pass

    # Windows — ctypes GlobalMemoryStatusEx (instant, no subprocess)
    if gb == 0.0 and platform.system() == "Windows":
        try:
            import ctypes
            class _MEM(ctypes.Structure):
                _fields_ = [
                    ("dwLength",                ctypes.c_ulong),
                    ("dwMemoryLoad",            ctypes.c_ulong),
                    ("ullTotalPhys",            ctypes.c_ulonglong),
                    ("ullAvailPhys",            ctypes.c_ulonglong),
                    ("ullTotalPageFile",        ctypes.c_ulonglong),
                    ("ullAvailPageFile",        ctypes.c_ulonglong),
                    ("ullTotalVirtual",         ctypes.c_ulonglong),
                    ("ullAvailVirtual",         ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = _MEM(); stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            gb = stat.ullTotalPhys / 1024**3
        except Exception:
            pass

    if gb >= RECOMMENDED["ram_gb"]:
        status: Status = "pass"
        detail = "RAM suffisante pour toutes les fonctionnalités (IA, vidéo, base de données)"
    elif gb >= MINIMUM["ram_gb"]:
        status = "warn"
        detail = "Fonctionnel — des swap peuvent apparaître avec ≥ 8 caméras simultanées"
    else:
        status = "fail"
        detail = f"RAM insuffisante — minimum {MINIMUM['ram_gb']} Go requis (PostgreSQL + IA engine + Frontend)"

    return Check(
        id="ram",
        label="Mémoire RAM",
        status=status,
        value=f"{gb:.1f} Go",
        expected=f"≥ {MINIMUM['ram_gb']} Go (recommandé {RECOMMENDED['ram_gb']}+ Go)",
        detail=detail,
        technical=f"Mémoire physique totale détectée : {gb:.2f} Go",
    )


# ---------------------------------------------------------------------------
# Stockage
# ---------------------------------------------------------------------------
def check_disk() -> Check:
    try:
        stat = shutil.disk_usage("/")
        free_gb = stat.free / 1024**3
        total_gb = stat.total / 1024**3
    except Exception:
        # Windows
        out = _run(["wmic", "logicaldisk", "get", "FreeSpace,Size", "/format:csv"])
        free_gb, total_gb = 0.0, 0.0
        for line in out.splitlines():
            parts = line.split(",")
            if len(parts) >= 3 and parts[1].isdigit():
                free_gb = int(parts[1]) / 1024**3
                total_gb = int(parts[2]) / 1024**3
                break

    if free_gb >= RECOMMENDED["disk_gb"]:
        status: Status = "pass"
        detail = "Espace suffisant pour les modèles IA, vidéos et preuves long terme"
    elif free_gb >= MINIMUM["disk_gb"]:
        status = "warn"
        detail = f"Espace limité — évitez plus de 30 jours de rétention vidéo. Recommandé : {RECOMMENDED['disk_gb']}+ Go libres"
    else:
        status = "fail"
        detail = (
            f"Espace insuffisant — minimum {MINIMUM['disk_gb']} Go libres requis "
            f"(modèles YOLO ≈ 200 Mo, PostgreSQL data, MinIO evidence store)"
        )

    return Check(
        id="disk",
        label="Stockage disponible",
        status=status,
        value=f"{free_gb:.0f} Go libres / {total_gb:.0f} Go total",
        expected=f"≥ {MINIMUM['disk_gb']} Go libres (recommandé {RECOMMENDED['disk_gb']}+ Go)",
        detail=detail,
        technical=f"df / — free={free_gb:.1f} Go total={total_gb:.1f} Go",
    )


# ---------------------------------------------------------------------------
# GPU / CUDA
# ---------------------------------------------------------------------------
def check_gpu() -> list[Check]:
    checks: list[Check] = []
    smi_out = _run(["nvidia-smi",
                    "--query-gpu=name,memory.total,driver_version,compute_cap",
                    "--format=csv,noheader,nounits"], timeout=10)

    if not smi_out:
        checks.append(Check(
            id="gpu_present",
            label="GPU NVIDIA / CUDA",
            status="warn",
            value="Aucun GPU NVIDIA détecté",
            expected="NVIDIA avec CUDA 11+ (optionnel mais recommandé)",
            detail=(
                "L'application fonctionnera en mode CPU-only : max 2 caméras, ~3 FPS. "
                "Un GPU CUDA multiplie les performances par 5–20×."
            ),
            technical="nvidia-smi non disponible ou GPU absent. CPU fallback activé.",
        ))
        return checks

    lines = [l.strip() for l in smi_out.strip().splitlines() if l.strip()]
    for i, line in enumerate(lines):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        name = parts[0]
        vram_mb = float(parts[1]) if parts[1].replace(".", "").isdigit() else 0.0
        driver = parts[2] if len(parts) > 2 else "?"
        compute = parts[3] if len(parts) > 3 else "?"

        # Parse CUDA major
        cuda_major = 0
        m = re.match(r"(\d+)", compute)
        if m:
            cuda_major = int(m.group(1))

        # GPU present
        checks.append(Check(
            id=f"gpu_{i}_present",
            label=f"GPU #{i+1} — {name}",
            status="pass",
            value=f"{name} — {vram_mb:.0f} MiB VRAM",
            expected="GPU NVIDIA avec CUDA",
            detail=_gpu_tier_description(vram_mb),
            technical=f"Driver: {driver} | Compute Capability: {compute} | VRAM: {vram_mb:.0f} MiB",
        ))

        # VRAM
        if vram_mb >= RECOMMENDED["gpu_vram_mb"]:
            vram_status: Status = "pass"
            vram_detail = "VRAM suffisante pour YOLO v8s/m avec batch processing"
        elif vram_mb >= 3000:
            vram_status = "warn"
            vram_detail = "VRAM correcte pour yolov8n — performances limitées en multi-caméra"
        else:
            vram_status = "fail"
            vram_detail = "VRAM insuffisante pour l'inférence YOLO temps-réel — fallback CPU"

        checks.append(Check(
            id=f"gpu_{i}_vram",
            label=f"GPU #{i+1} — VRAM",
            status=vram_status,
            value=f"{vram_mb:.0f} MiB",
            expected=f"≥ {MINIMUM['gpu_vram_mb']} MiB (recommandé {RECOMMENDED['gpu_vram_mb']} MiB+)",
            detail=vram_detail,
            technical=f"nvidia-smi memory.total = {vram_mb:.0f} MiB",
        ))

        # CUDA Compute Capability check
        # CC 7.x (Pascal/Turing) = CUDA 11 support
        # CC 8.x (Ampere/Ada)    = CUDA 12 support  ← RTX 30xx/40xx
        # CC 9.x (Hopper/Blackwell) = CUDA 12+ support
        # Minimum: CC 6.0 (Pascal), Recommended: CC 8.0+
        CC_MIN = 6          # CC 6.0 = GTX 10xx, CUDA 11 minimum
        CC_RECOMMENDED = 8  # CC 8.0 = RTX 30xx+, best ONNX/TRT support
        if cuda_major >= CC_RECOMMENDED:
            cuda_status: Status = "pass"
            cuda_detail = f"CC {compute} (Ampere/Ada/Hopper) — compatibilité complète ONNX Runtime GPU + TensorRT"
        elif cuda_major >= CC_MIN:
            cuda_status = "warn"
            cuda_detail = f"CC {compute} (Pascal/Turing) — fonctionnel, performances ONNX légèrement réduites"
        else:
            cuda_status = "fail"
            cuda_detail = f"CC {compute} trop ancienne — Compute Capability ≥ 6.0 requis (GTX 10xx minimum)"

        checks.append(Check(
            id=f"gpu_{i}_cuda",
            label=f"GPU #{i+1} — Compute Capability",
            status=cuda_status,
            value=f"CC {compute} / Driver {driver}",
            expected=f"CC ≥ {CC_MIN}.0 (recommandé CC {CC_RECOMMENDED}.0+)",
            detail=cuda_detail,
            technical=f"Compute Capability: {compute} | nvidia-smi driver: {driver}",
        ))

    return checks


def _gpu_tier_description(vram_mb: float) -> str:
    if vram_mb >= 16000:
        return "Tier MAX — 48 caméras, yolov8l, batch 32, 30 FPS"
    if vram_mb >= 8000:
        return "Tier ULTRA — 24 caméras, yolov8m, batch 16, 25 FPS"
    if vram_mb >= 6000:
        return "Tier HIGH — 16 caméras, yolov8s, batch 8, 15 FPS"
    if vram_mb >= 3000:
        return "Tier STANDARD — 8 caméras, yolov8n, batch 4, 10 FPS"
    return "Tier CPU-only — 2 caméras, yolov8n, batch 1, 3 FPS"


# ---------------------------------------------------------------------------
# OS & Architecture
# ---------------------------------------------------------------------------
def check_os() -> Check:
    system = platform.system()
    release = platform.release()
    machine = platform.machine()
    version = platform.version()

    if system == "Linux":
        status: Status = "pass"
        detail = "Linux — déploiement natif Docker, performances optimales"
    elif system == "Windows":
        # Check WSL2 availability
        build_match = re.search(r"(\d{5})", version)
        build = int(build_match.group(1)) if build_match else 0
        if build >= 19041:
            status = "pass"
            detail = "Windows 10/11 build ≥ 19041 — WSL2 supporté, environnement Linux automatique"
        else:
            status = "fail"
            detail = f"Windows build {build} — WSL2 requiert build ≥ 19041 (Windows 10 v2004+)"
    elif system == "Darwin":
        status = "warn"
        detail = "macOS — fonctionnel mais non officiellement supporté. Pas de CUDA natif."
    else:
        status = "warn"
        detail = f"OS non testé ({system}) — un comportement inattendu est possible"

    return Check(
        id="os",
        label="Système d'exploitation",
        status=status,
        value=f"{system} {release} ({machine})",
        expected="Windows 10 build 19041+ / Ubuntu 20.04+ / Debian 11+",
        detail=detail,
        technical=f"platform.version() = {version}",
    )


# ---------------------------------------------------------------------------
# Réseau
# ---------------------------------------------------------------------------
def check_network() -> Check:
    import urllib.request
    try:
        urllib.request.urlopen("https://github.com", timeout=3)
        status: Status = "pass"
        detail = "Connectivité Internet confirmée — téléchargements disponibles"
        value = "En ligne"
    except Exception as e:
        status = "fail"
        detail = "Pas de connexion Internet — requis pour télécharger Docker, Go, Node, Python, modèles YOLO (~800 Mo)"
        value = "Hors ligne"

    return Check(
        id="network",
        label="Connexion Internet",
        status=status,
        value=value,
        expected="Accès à github.com (téléchargements des dépendances)",
        detail=detail,
        technical="urllib.request.urlopen('https://github.com', timeout=5)",
    )


# ---------------------------------------------------------------------------
# Rapport global
# ---------------------------------------------------------------------------
def run_all() -> dict:
    checks: list[Check] = []
    checks += check_cpu()
    checks.append(check_ram())
    checks.append(check_disk())
    checks.append(check_os())
    checks.append(check_network())
    checks += check_gpu()

    results = [asdict(c) for c in checks]
    fails = [c for c in checks if c.status == "fail"]
    warns = [c for c in checks if c.status == "warn"]

    if fails:
        overall = "fail"
        summary = f"{len(fails)} critère(s) bloquant(s) — installation impossible sur cette machine"
    elif warns:
        overall = "warn"
        summary = f"{len(warns)} avertissement(s) — installation possible avec des performances réduites"
    else:
        overall = "pass"
        summary = "Tous les prérequis sont satisfaits — performances optimales garanties"

    # GPU tier
    gpu_tier = _detect_gpu_tier()

    return {
        "overall": overall,
        "summary": summary,
        "gpu_tier": gpu_tier,
        "checks": results,
        "machine": {
            "os": platform.system(),
            "arch": platform.machine(),
            "python": sys.version,
        },
    }


def _detect_gpu_tier() -> dict:
    smi = _run(["nvidia-smi",
                "--query-gpu=name,memory.total,compute_cap",
                "--format=csv,noheader,nounits"], timeout=10)
    if not smi:
        return {"tier": "cpu-only", "label": "CPU-only", "max_cameras": 2,
                "yolo_model": "yolov8n.onnx", "batch_size": 1, "target_fps": 3}
    parts = [p.strip() for p in smi.splitlines()[0].split(",")]
    vram = float(parts[1]) if len(parts) > 1 and parts[1].replace(".", "").isdigit() else 0
    if vram >= 16000:
        return {"tier": "max", "label": "Max (RTX 4090/5090)", "max_cameras": 48,
                "yolo_model": "yolov8l.onnx", "batch_size": 32, "target_fps": 30}
    if vram >= 8000:
        return {"tier": "ultra", "label": "Ultra (RTX 4070–5060 8-16 Go)", "max_cameras": 24,
                "yolo_model": "yolov8m.onnx", "batch_size": 16, "target_fps": 25}
    if vram >= 6000:
        return {"tier": "high", "label": "High (RTX 3060–4060 6-12 Go)", "max_cameras": 16,
                "yolo_model": "yolov8s.onnx", "batch_size": 8, "target_fps": 15}
    if vram >= 3000:
        return {"tier": "standard", "label": "Standard (GTX 1060–2080 4-8 Go)", "max_cameras": 8,
                "yolo_model": "yolov8n.onnx", "batch_size": 4, "target_fps": 10}
    return {"tier": "cpu-only", "label": "CPU-only (GPU insuffisant)", "max_cameras": 2,
            "yolo_model": "yolov8n.onnx", "batch_size": 1, "target_fps": 3}


if __name__ == "__main__":
    result = run_all()
    print(json.dumps(result, ensure_ascii=False, indent=2))
