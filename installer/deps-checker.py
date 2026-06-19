#!/usr/bin/env python3
"""
CitéVision v2 — Dependency Checker & Installer
Vérifie toutes les dépendances nécessaires et les installe si absentes.
Diffuse l'état en temps réel via stdout (SSE depuis setup-server.py).
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

Status = Literal["ok", "missing", "outdated", "installing", "error"]

ROOT = Path(__file__).resolve().parent.parent
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"


@dataclass
class Dep:
    id: str
    name: str
    status: Status
    version: str = ""
    required: str = ""
    note: str = ""
    install_cmd: str = ""
    critical: bool = True


def _run(cmd: list[str], timeout: int = 10) -> tuple[int, str, str]:
    try:
        kwargs: dict = dict(
            capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
        )
        if platform.system() == "Windows":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        r = subprocess.run(cmd, **kwargs)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return 1, "", "not found"
    except Exception as e:
        return 1, "", str(e)


def _ver(s: str) -> tuple[int, ...]:
    m = re.search(r"(\d+)\.(\d+)", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    return (0, 0)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_python() -> Dep:
    code, out, _ = _run([sys.executable, "--version"])
    ver = out or ""
    v = _ver(ver)
    if v >= (3, 12):
        return Dep("python", "Python 3.12+", "ok", ver, "≥ 3.12",
                   "Runtime de l'AI engine et des scripts d'installation")
    if v >= (3, 10):
        return Dep("python", "Python 3.12+", "outdated", ver, "≥ 3.12",
                   "Version trop ancienne — certains modules AI engine nécessitent 3.12+",
                   install_cmd="Télécharger https://python.org/downloads/")
    return Dep("python", "Python 3.12+", "missing", ver or "non trouvé", "≥ 3.12",
               "Python est requis pour l'AI engine et les scripts d'installation",
               install_cmd="https://python.org/downloads/", critical=True)


def check_docker() -> Dep:
    code, out, _ = _run(["docker", "--version"])
    if code == 0 and out:
        # Check if daemon is running
        dc, _, _ = _run(["docker", "info"], timeout=8)
        if dc == 0:
            return Dep("docker", "Docker Engine", "ok", out, "≥ 20.10",
                       "Conteneurs PostgreSQL, Redis, MQTT, MinIO, go2rtc")
        return Dep("docker", "Docker Engine", "error", out, "≥ 20.10",
                   "Docker installé mais daemon non démarré — lancez 'sudo service docker start'",
                   install_cmd="sudo service docker start")
    install = (
        "curl -fsSL https://get.docker.com | sh && sudo usermod -aG docker $USER"
        if IS_LINUX else
        "Télécharger Docker Desktop: https://docker.com/products/docker-desktop"
    )
    return Dep("docker", "Docker Engine", "missing", "non trouvé", "≥ 20.10",
               "Docker est requis pour tous les services infrastructure (DB, cache, broker, stockage)",
               install_cmd=install, critical=True)


def check_docker_compose() -> Dep:
    # Docker Compose v2 (plugin)
    code, out, _ = _run(["docker", "compose", "version"])
    if code == 0 and out:
        return Dep("docker_compose", "Docker Compose v2", "ok", out, "≥ 2.0",
                   "Orchestration des services infrastructure")
    # Standalone
    code2, out2, _ = _run(["docker-compose", "--version"])
    if code2 == 0:
        return Dep("docker_compose", "Docker Compose v2", "outdated", out2, "≥ 2.0",
                   "docker-compose v1 détecté — utilisez 'docker compose' (v2, plugin Docker)")
    return Dep("docker_compose", "Docker Compose v2", "missing", "non trouvé", "≥ 2.0",
               "Inclus dans Docker Engine moderne. Mettez à jour Docker.",
               install_cmd="sudo apt-get update && sudo apt-get install docker-compose-plugin")


def check_go() -> Dep:
    code, out, _ = _run(["go", "version"])
    if code == 0:
        v = _ver(out)
        if v >= (1, 22):
            return Dep("go", "Go 1.22+", "ok", out, "≥ 1.22",
                       "Backend API (Go), Rules Engine")
        return Dep("go", "Go 1.22+", "outdated", out, "≥ 1.22",
                   f"Go {v[0]}.{v[1]} trop ancien — generics et améliorations stdlib requis depuis 1.22",
                   install_cmd="curl -fsSL https://go.dev/dl/go1.22.5.linux-amd64.tar.gz | sudo tar -C /usr/local -xz")
    install = (
        "curl -fsSL https://go.dev/dl/go1.22.5.linux-amd64.tar.gz | sudo tar -C /usr/local -xz"
        if IS_LINUX else
        "Télécharger: https://go.dev/dl/go1.22.5.windows-amd64.msi"
    )
    return Dep("go", "Go 1.22+", "missing", "non trouvé", "≥ 1.22",
               "Requis pour compiler et lancer le backend API et le moteur de règles",
               install_cmd=install, critical=True)


def check_node() -> Dep:
    code, out, _ = _run(["node", "--version"])
    if code == 0:
        v = _ver(out)
        if v >= (20, 0):
            return Dep("node", "Node.js 20+", "ok", out, "≥ 20 LTS",
                       "Frontend React (Vite), build et dev server")
        return Dep("node", "Node.js 20+", "outdated", out, "≥ 20 LTS",
                   f"Node {out} trop ancien — React 18 et Vite 6 requièrent Node 20+",
                   install_cmd="curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -")
    install = (
        "curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt-get install -y nodejs"
        if IS_LINUX else
        "Télécharger: https://nodejs.org/en/download"
    )
    return Dep("node", "Node.js 20+", "missing", "non trouvé", "≥ 20 LTS",
               "Requis pour le frontend React/Vite (dev server et build de production)",
               install_cmd=install, critical=True)


def check_npm() -> Dep:
    code, out, _ = _run(["npm", "--version"])
    if code == 0:
        return Dep("npm", "npm", "ok", f"npm {out}", "≥ 9",
                   "Gestionnaire de paquets Node.js")
    return Dep("npm", "npm", "missing", "non trouvé", "≥ 9",
               "npm est inclus avec Node.js — réinstallez Node.js",
               install_cmd="npm est inclus avec Node.js")


def check_ffmpeg() -> Dep:
    code, out, _ = _run(["ffmpeg", "-version"])
    if code == 0:
        first_line = out.splitlines()[0] if out else ""
        return Dep("ffmpeg", "FFmpeg", "ok", first_line[:60], "≥ 4.x",
                   "Transcoding RTSP, capture frames, test caméra")
    install = (
        "sudo apt-get install -y ffmpeg" if IS_LINUX
        else "winget install Gyan.FFmpeg"
    )
    return Dep("ffmpeg", "FFmpeg", "missing", "non trouvé", "≥ 4.x",
               "Requis pour l'ingestion RTSP, le test des caméras et l'enregistrement vidéo",
               install_cmd=install, critical=False)


def check_git() -> Dep:
    code, out, _ = _run(["git", "--version"])
    if code == 0:
        return Dep("git", "Git", "ok", out, "≥ 2.x", "Gestion de version, submodules")
    return Dep("git", "Git", "missing", "non trouvé", "≥ 2.x",
               "Git est recommandé pour les mises à jour",
               install_cmd="sudo apt-get install -y git", critical=False)


def check_cuda_toolkit() -> Dep:
    """Vérifie la présence de nvcc (CUDA Toolkit)."""
    code, out, _ = _run(["nvcc", "--version"])
    if code == 0:
        v = _ver(out)
        if v >= (11, 0):
            return Dep("cuda_toolkit", "CUDA Toolkit 11+", "ok", out.splitlines()[-1] if out else out,
                       "≥ 11.0", "Compilation ONNX Runtime GPU, TensorRT")
        return Dep("cuda_toolkit", "CUDA Toolkit 11+", "outdated", out, "≥ 11.0",
                   "CUDA trop ancien", critical=False)
    # nvcc absent mais GPU présent via nvidia-smi → CUDA Runtime present sans toolkit
    smi_code, smi_out, _ = _run(["nvidia-smi"])
    if smi_code == 0:
        return Dep("cuda_toolkit", "CUDA Runtime (nvidia-smi)", "ok",
                   "Runtime détecté (nvcc absent — toolkit complet optionnel)", "Runtime CUDA",
                   "CUDA Runtime disponible via driver NVIDIA. ONNX Runtime GPU fonctionnel.",
                   critical=False)
    return Dep("cuda_toolkit", "CUDA Toolkit / Runtime", "missing", "non trouvé",
               "Optionnel (GPU NVIDIA requis)",
               "Sans CUDA : fallback CPU-only (2 caméras max, 3 FPS). "
               "Installer: https://developer.nvidia.com/cuda-downloads",
               critical=False)


def check_jq() -> Dep:
    code, out, _ = _run(["jq", "--version"])
    if code == 0:
        return Dep("jq", "jq (JSON CLI)", "ok", out, "≥ 1.6", "Scripts de validation et de diagnostic")
    return Dep("jq", "jq (JSON CLI)", "missing", "non trouvé", "≥ 1.6",
               "Utilisé par les scripts de validation",
               install_cmd="sudo apt-get install -y jq", critical=False)


def check_cmake() -> Dep:
    code, out, _ = _run(["cmake", "--version"])
    if code == 0:
        v = _ver(out)
        if v >= (3, 20):
            return Dep("cmake", "CMake 3.20+", "ok", out.splitlines()[0], "≥ 3.20",
                       "Compilation du Video Engine C++")
        return Dep("cmake", "CMake 3.20+", "outdated", out.splitlines()[0], "≥ 3.20",
                   "Video Engine C++ requiert CMake 3.20+",
                   install_cmd="sudo apt-get install -y cmake", critical=False)
    return Dep("cmake", "CMake 3.20+", "missing", "non trouvé", "≥ 3.20",
               "Requis uniquement pour la compilation du Video Engine C++ (optionnel en mode conteneur)",
               install_cmd="sudo apt-get install -y cmake", critical=False)


def check_wsl() -> Dep:
    """Windows only — vérifie WSL2."""
    if not IS_WINDOWS:
        return Dep("wsl", "WSL2 (Windows uniquement)", "ok", "N/A — Linux natif",
                   "Requis sur Windows", "Environnement Linux natif détecté")
    code, out, _ = _run(["wsl", "--status"])
    if code == 0 and out:
        if "2" in out:
            return Dep("wsl", "WSL2", "ok", "WSL2 actif", "WSL2 + Ubuntu 24.04",
                       "Environnement Linux pour tous les services backend")
        return Dep("wsl", "WSL2", "outdated", "WSL1 détecté", "WSL2 requis",
                   "Convertir : wsl --set-default-version 2",
                   install_cmd="wsl --set-default-version 2")
    return Dep("wsl", "WSL2", "missing", "non détecté", "WSL2 + Ubuntu 24.04",
               "WSL2 est requis sur Windows pour exécuter les services Linux (Docker natif, backend, AI engine)",
               install_cmd="wsl --install -d Ubuntu-24.04 (redémarrage requis)", critical=True)


def check_yolo_model() -> Dep:
    model_path = ROOT / "ai-engine" / "models" / "yolov8n.onnx"
    if model_path.exists():
        size_mb = model_path.stat().st_size / 1024 / 1024
        return Dep("yolo_model", "Modèle YOLO (yolov8n.onnx)", "ok",
                   f"{size_mb:.1f} Mo", "≥ 6 Mo",
                   "Modèle de détection d'objets (personnes, véhicules, etc.)")
    return Dep("yolo_model", "Modèle YOLO (yolov8n.onnx)", "missing",
               "non trouvé", "yolov8n.onnx (≈ 6 Mo)",
               "Modèle de détection requis pour toute analyse vidéo. "
               f"Attendu : {model_path}",
               install_cmd="bash scripts/download-models.sh",
               critical=True)


def check_frontend_deps() -> Dep:
    nm = ROOT / "frontend" / "node_modules"
    if nm.exists() and (nm / ".package-lock.json").exists() or (nm / "react").exists():
        return Dep("frontend_deps", "Dépendances frontend (node_modules)", "ok",
                   "installées", "npm install",
                   "React, Vite, TailwindCSS et toutes les librairies UI")
    return Dep("frontend_deps", "Dépendances frontend (node_modules)", "missing",
               "non installées", "npm install",
               "Requis pour lancer ou builder le frontend React",
               install_cmd="cd frontend && npm install")


def check_python_venv() -> Dep:
    venv = ROOT / "ai-engine" / ".venv"
    if venv.exists():
        # Check if deps installed
        site_packages = venv / "lib"
        if site_packages.exists():
            return Dep("python_venv", "Virtualenv AI Engine (.venv)", "ok",
                       str(venv), "pip install -r requirements.txt",
                       "Environnement Python isolé pour l'AI engine")
    return Dep("python_venv", "Virtualenv AI Engine (.venv)", "missing",
               "non créé", "python3 -m venv + pip install",
               "Environnement Python isolé pour l'AI engine et ses dépendances ONNX",
               install_cmd="cd ai-engine && python3.12 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt")


# ---------------------------------------------------------------------------
# Run all checks
# ---------------------------------------------------------------------------
def run_all(mode: str = "check") -> dict:
    deps: list[Dep] = [
        check_python(),
        check_docker(),
        check_docker_compose(),
        check_go(),
        check_node(),
        check_npm(),
        check_ffmpeg(),
        check_git(),
        check_cuda_toolkit(),
        check_jq(),
        check_cmake(),
        check_yolo_model(),
        check_frontend_deps(),
        check_python_venv(),
    ]
    if IS_WINDOWS:
        deps.insert(2, check_wsl())

    missing_critical = [d for d in deps if d.critical and d.status in ("missing", "outdated", "error")]
    missing_optional = [d for d in deps if not d.critical and d.status in ("missing", "outdated")]

    return {
        "deps": [asdict(d) for d in deps],
        "missing_critical": [d.id for d in missing_critical],
        "missing_optional": [d.id for d in missing_optional],
        "ready": len(missing_critical) == 0,
        "summary": (
            "Toutes les dépendances critiques sont présentes"
            if not missing_critical
            else f"{len(missing_critical)} dépendance(s) critique(s) manquante(s)"
        ),
    }


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
def _to_wsl_path(win_path: Path) -> str:
    """Convert a Windows absolute path to its WSL /mnt/... equivalent."""
    import os
    # Use posix string representation which Path gives us
    s = win_path.as_posix()               # C:/Users/gheno/... (forward slashes)
    if len(s) >= 2 and s[1] == ":":
        drive = s[0].lower()
        rest  = s[2:]                     # /Users/gheno/...
        return f"/mnt/{drive}{rest}"
    return s


def _win_path_exists(p: Path) -> bool:
    """Return True if the path exists on disk (Windows or Unix)."""
    return p.exists()


# ---------------------------------------------------------------------------
# SSE install stream
# ---------------------------------------------------------------------------
def install_stream():
    """
    Générateur SSE : installe les dépendances manquantes via setup-wsl.sh.
    Sur Windows, le script est exécuté via WSL avec la conversion de chemin.
    """
    def emit(event: str, **kw) -> str:
        return f"data: {json.dumps({'event': event, **kw}, ensure_ascii=False)}\n\n"

    yield emit("step", message="Démarrage de l'installation CitéVision v2…")

    setup_script = ROOT / "scripts" / "setup-wsl.sh"
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "installer.log"

    if not setup_script.exists():
        yield emit("error", message=f"Script introuvable : {setup_script}")
        return

    # ── Build the command depending on OS ─────────────────────
    popen_kwargs: dict = dict(
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        stdin=subprocess.DEVNULL,
    )

    if IS_WINDOWS:
        yield emit("step", message="Démarrage de l'installation automatique…")
        # Convert Windows paths to WSL mount paths
        wsl_script   = _to_wsl_path(setup_script)
        wsl_log      = _to_wsl_path(log_file)
        wsl_log_dir  = _to_wsl_path(log_dir)
        cmd = [
            "wsl", "--",
            "bash", wsl_script,
            "--silent",
            f"--log-file={wsl_log}",
        ]
        # Run wsl mkdir -p to ensure log dir exists in WSL
        subprocess.run(
            ["wsl", "--", "mkdir", "-p", wsl_log_dir],
            capture_output=True, timeout=10,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        popen_kwargs["text"] = True
        popen_kwargs["encoding"] = "utf-8"
        popen_kwargs["errors"] = "replace"
    else:
        yield emit("step", message="Démarrage de l'installation Linux/macOS…")
        cmd = ["bash", str(setup_script), "--silent", f"--log-file={log_file}"]
        popen_kwargs["text"] = True

    yield emit("ok", message=f"Commande : {' '.join(cmd[:4])}...")

    import queue as _queue
    import threading as _threading

    line_q: _queue.Queue = _queue.Queue()

    def _run_proc() -> None:
        try:
            proc = subprocess.Popen(cmd, **popen_kwargs)
            for raw in proc.stdout:  # type: ignore
                line_q.put(("line", raw.rstrip()))
            proc.wait()
            line_q.put(("done", proc.returncode))
        except FileNotFoundError:
            line_q.put(("missing", None))
        except Exception as exc:
            import traceback as _tb
            line_q.put(("exception", _tb.format_exc()))

    t = _threading.Thread(target=_run_proc, daemon=True)
    t.start()

    heartbeat_msgs = [
        "Installation en cours — veuillez patienter...",
        "Mise à jour des paquets système...",
        "Téléchargement des dépendances...",
        "Configuration de l'environnement...",
        "Vérification des composants...",
    ]
    hb_idx = 0

    while True:
        try:
            kind, payload = line_q.get(timeout=2.0)
        except _queue.Empty:
            # Heartbeat — let the UI know we're still running
            yield emit("heartbeat", message=heartbeat_msgs[hb_idx % len(heartbeat_msgs)])
            hb_idx += 1
            continue

        if kind == "done":
            rc = payload
            if rc == 0:
                yield emit("done", message="Installation terminée avec succès !")
            else:
                yield emit("error", message=f"Erreur lors de l'installation (code {rc})")
            break
        elif kind == "missing":
            if IS_WINDOWS:
                yield emit("error", message=(
                    "WSL introuvable.\n"
                    "Ouvrez PowerShell en admin et exécutez : wsl --install\n"
                    "Redémarrez Windows puis relancez l'installation."
                ))
            else:
                yield emit("error", message="bash introuvable sur ce système.")
            break
        elif kind == "exception":
            yield emit("error", message=payload)
            break
        else:
            # kind == "line"
            line = payload
            if not line:
                continue
            low = line.lower()
            if "[err]" in low or "error" in low or "failed" in low:
                evt = "error"
            elif "[ok]" in low or "success" in low or "complete" in low:
                evt = "ok"
            elif "[warn]" in low or "warning" in low or "skipped" in low:
                evt = "warn"
            elif "===" in line or "[step]" in low:
                evt = "step"
            else:
                evt = "info"
            yield emit(evt, message=line)


# ---------------------------------------------------------------------------
# Launch stream — starts services via start-linux.sh
# ---------------------------------------------------------------------------
def launch_stream():
    """SSE generator: runs start-linux.sh via WSL then polls for port 5174."""
    def emit(event: str, **kw) -> str:
        return f"data: {json.dumps({'event': event, **kw}, ensure_ascii=False)}\n\n"

    start_script = ROOT / "scripts" / "start-linux.sh"
    if not start_script.exists():
        yield emit("error", message=f"Script introuvable : {start_script}")
        return

    yield emit("step", message="Demarrage des services CitéVision...")

    import queue as _queue, threading as _threading, urllib.request as _urllib

    def _poll_port(port: int, timeout: int = 120) -> bool:
        import socket as _socket, time as _time
        deadline = _time.time() + timeout
        while _time.time() < deadline:
            try:
                with _socket.create_connection(("localhost", port), timeout=2):
                    return True
            except Exception:
                _time.sleep(3)
        return False

    line_q: _queue.Queue = _queue.Queue()

    def _run() -> None:
        try:
            wsl_script = _to_wsl_path(start_script)
            import traceback as _tb
            kwargs: dict = dict(
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                bufsize=1, stdin=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="replace",
            )
            if IS_WINDOWS:
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                env = os.environ.copy(); env["PYTHONIOENCODING"] = "utf-8"
                kwargs["env"] = env
                cmd = ["wsl", "--", "bash", wsl_script]
            else:
                cmd = ["bash", str(start_script)]
            proc = subprocess.Popen(cmd, **kwargs)
            for raw in proc.stdout:  # type: ignore
                line_q.put(("line", raw.rstrip()))
            proc.wait()
            line_q.put(("done", proc.returncode))
        except FileNotFoundError:
            line_q.put(("missing", None))
        except Exception:
            import traceback as _tb
            line_q.put(("exception", _tb.format_exc()))

    t = _threading.Thread(target=_run, daemon=True)
    t.start()

    heartbeat_msgs = [
        "Démarrage du backend Go...",
        "Compilation des modules Go (premier démarrage)...",
        "Démarrage du frontend Vite...",
        "Démarrage de l'AI engine...",
        "Services en cours d'initialisation...",
    ]
    hb_idx = 0

    while True:
        try:
            kind, payload = line_q.get(timeout=3.0)
        except _queue.Empty:
            yield emit("heartbeat", message=heartbeat_msgs[hb_idx % len(heartbeat_msgs)])
            hb_idx += 1
            continue

        if kind == "done":
            rc = payload
            if rc == 0:
                yield emit("step", message="Services démarrés — vérification de l'interface...")
                # Poll for frontend on port 5174
                if _poll_port(5174, timeout=120):
                    yield emit("launch_ready", message="http://localhost:5174")
                else:
                    yield emit("warn", message="Timeout — l'interface met plus de temps que prévu. Vérifiez logs/frontend.log")
                    yield emit("launch_ready", message="http://localhost:5174")
            else:
                yield emit("error", message=f"Erreur démarrage (code {rc}) — consultez logs/backend.log")
            break
        elif kind in ("missing", "exception"):
            yield emit("error", message=str(payload or "Script introuvable"))
            break
        else:
            line = payload
            if not line:
                continue
            low = line.lower()
            if "[ok]" in low or "healthy" in low or "ready" in low:
                evt = "ok"
            elif "[warn]" in low or "warn" in low or "timeout" in low:
                evt = "warn"
            elif "[fail]" in low or "error" in low or "fail" in low:
                evt = "error"
            elif "===" in line or "[info]" in low:
                evt = "step"
            else:
                evt = "info"
            yield emit(evt, message=line)


if __name__ == "__main__":
    result = run_all()
    print(json.dumps(result, ensure_ascii=False, indent=2))
