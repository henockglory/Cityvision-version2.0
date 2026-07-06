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
import socket
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

Status = Literal["ok", "missing", "outdated", "installing", "error"]

ROOT = Path(__file__).resolve().parent.parent
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"
WINDOWS_SERVICE_NAME = "citevision"

# Ports requis par CitéVision v2
REQUIRED_PORTS = {
    5174: "Frontend Vite",
    8081: "Backend API (Go)",
    8001: "AI Engine (Python)",
    8010: "Rules Engine",
    1984: "go2rtc",
    5432: "PostgreSQL (natif)",
    5433: "PostgreSQL (Docker v2)",
    6379: "Redis (natif)",
    6380: "Redis (Docker v2)",
    9003: "MinIO API",
    9004: "MinIO Console",
}


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
            encoding="utf-8", errors="replace",
        )
        if platform.system() == "Windows":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        r = subprocess.run(cmd, **kwargs)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return 1, "", "not found"
    except Exception as e:
        return 1, "", str(e)


def _wsl_run(cmd: list[str], timeout: int = 10) -> tuple[int, str, str]:
    """Exécute une commande dans WSL (Windows seulement)."""
    if not IS_WINDOWS:
        return _run(cmd, timeout)
    return _run(["wsl", "--"] + cmd, timeout)


def _ver(s: str) -> tuple[int, ...]:
    m = re.search(r"(\d+)\.(\d+)", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    return (0, 0)


def _port_in_use(port: int) -> bool:
    """True si le port est occupé (service écoute)."""
    try:
        with socket.create_connection(("localhost", port), timeout=1):
            return True
    except Exception:
        return False


def _port_free(port: int) -> bool:
    """True si le port est libre (pas d'écoute = bon pour installation)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", port))
            return True
    except OSError:
        return False


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


def _docker_run(cmd: list[str], timeout: int = 10) -> tuple[int, str, str]:
    """Run a docker command: via WSL on Windows, directly on Linux."""
    if IS_WINDOWS:
        return _wsl_run(cmd, timeout)
    return _run(cmd, timeout)


def check_docker() -> Dep:
    code, out, _ = _docker_run(["docker", "--version"])
    if code == 0 and out:
        dc, _, _ = _docker_run(["docker", "info"], timeout=12)
        if dc == 0:
            return Dep("docker", "Docker Engine", "ok", out, "≥ 20.10",
                       "Conteneurs PostgreSQL, Redis, MQTT, MinIO, go2rtc")
        return Dep("docker", "Docker Engine", "error", out, "≥ 20.10",
                   "Docker installé mais daemon non démarré — relancez via bash scripts/start-linux.sh (démarre dockerd natif WSL)",
                   install_cmd="bash scripts/start-linux.sh")
    install = "curl -fsSL https://get.docker.com | sh && sudo usermod -aG docker $USER"
    return Dep("docker", "Docker Engine", "missing", "non trouvé", "≥ 20.10",
               "Docker est requis pour tous les services infrastructure (DB, cache, broker, stockage)",
               install_cmd=install, critical=True)


def check_docker_running() -> Dep:
    """Vérifie que le daemon Docker est actif, pas juste installé."""
    code, out, err = _docker_run(["docker", "info"], timeout=12)
    if code == 0:
        ver_line = next((l for l in out.splitlines() if "Server Version" in l), "")
        ver = ver_line.split(":")[-1].strip() if ver_line else "actif"
        return Dep("docker_daemon", "Docker Daemon (actif)", "ok", ver, "daemon actif",
                   "Le daemon Docker répond correctement")
    code2, _, _ = _docker_run(["docker", "--version"])
    if code2 != 0:
        return Dep("docker_daemon", "Docker Daemon (actif)", "missing", "non installé",
                   "daemon actif", "Docker n'est pas installé",
                   install_cmd="curl -fsSL https://get.docker.com | sh", critical=False)
    return Dep("docker_daemon", "Docker Daemon (actif)", "error", "non démarré",
               "daemon actif",
               "Docker Engine natif installé mais dockerd inactif. "
               "Relancez: bash scripts/start-linux.sh (auto-démarre dockerd sur WSL)",
               install_cmd="bash scripts/start-linux.sh", critical=True)


def check_docker_group() -> Dep:
    """Vérifie que l'utilisateur courant est dans le groupe docker (Linux/WSL)."""
    if IS_WINDOWS:
        code, out, _ = _wsl_run(["id", "-Gn"])
        if code == 0:
            if "docker" in out.split():
                return Dep("docker_group", "Groupe docker (WSL)", "ok",
                           "utilisateur dans le groupe docker", "groupe docker",
                           "Pas besoin de sudo pour les commandes Docker dans WSL")
            return Dep("docker_group", "Groupe docker (WSL)", "missing",
                       "utilisateur absent du groupe docker", "groupe docker",
                       "Ajoutez l'utilisateur: sudo usermod -aG docker $USER && newgrp docker",
                       install_cmd="sudo usermod -aG docker $USER", critical=False)
        return Dep("docker_group", "Groupe docker (WSL)", "error", "WSL non disponible",
                   "groupe docker", "WSL requis pour vérifier le groupe docker", critical=False)

    if not IS_LINUX:
        return Dep("docker_group", "Groupe docker", "ok", "N/A",
                   "groupe docker", "Non applicable sur cet OS", critical=False)

    import grp
    try:
        username = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
        try:
            docker_gid = grp.getgrnam("docker").gr_gid
            user_groups = os.getgroups()
            if docker_gid in user_groups:
                return Dep("docker_group", "Groupe docker", "ok",
                           f"utilisateur '{username}' dans le groupe docker", "groupe docker",
                           "Commandes Docker sans sudo disponibles")
        except KeyError:
            pass
        return Dep("docker_group", "Groupe docker", "missing",
                   f"'{username}' absent du groupe docker", "groupe docker",
                   "Ajoutez l'utilisateur: sudo usermod -aG docker $USER && newgrp docker",
                   install_cmd="sudo usermod -aG docker $USER", critical=False)
    except Exception as e:
        return Dep("docker_group", "Groupe docker", "error", str(e), "groupe docker",
                   "Impossible de vérifier le groupe docker", critical=False)


def check_docker_compose() -> Dep:
    code, out, _ = _docker_run(["docker", "compose", "version"])
    if code == 0 and out:
        return Dep("docker_compose", "Docker Compose v2", "ok", out, "≥ 2.0",
                   "Orchestration des services infrastructure")
    code2, out2, _ = _docker_run(["docker-compose", "--version"])
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
    # On Windows, npm ships as npm.cmd — try both spellings
    npm_exe = shutil.which("npm") or ("npm.cmd" if IS_WINDOWS else "npm")
    code, out, _ = _run([npm_exe, "--version"])
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


def check_git_config() -> Dep:
    """Vérifie que git est configuré (user.email, user.name) — requis pour Go modules."""
    email_code, email, _ = _run(["git", "config", "--global", "user.email"])
    name_code, name, _ = _run(["git", "config", "--global", "user.name"])
    if email_code == 0 and email.strip() and name_code == 0 and name.strip():
        return Dep("git_config", "Git — configuration", "ok",
                   f"{name.strip()} <{email.strip()}>", "user.name + user.email",
                   "Git configuré correctement pour les modules Go")
    missing = []
    if not (name_code == 0 and name.strip()):
        missing.append("user.name")
    if not (email_code == 0 and email.strip()):
        missing.append("user.email")
    return Dep("git_config", "Git — configuration", "missing",
               f"Manquant: {', '.join(missing)}", "user.name + user.email",
               "Go modules requiert une identité git. "
               "Configurez: git config --global user.name 'Prénom Nom' && "
               "git config --global user.email 'vous@example.com'",
               install_cmd="git config --global user.name 'Votre Nom' && git config --global user.email 'vous@example.com'",
               critical=False)


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


def check_nvidia_container() -> Dep:
    """Vérifie nvidia-docker2 / nvidia-container-toolkit si GPU NVIDIA présent."""
    # D'abord vérifier si GPU présent
    smi_code, _, _ = _run(["nvidia-smi"])
    if smi_code != 0:
        return Dep("nvidia_container", "nvidia-container-toolkit", "ok",
                   "N/A — pas de GPU NVIDIA", "Optionnel (GPU requis)",
                   "Aucun GPU NVIDIA détecté — nvidia-container-toolkit non nécessaire",
                   critical=False)

    # GPU présent — vérifier le toolkit
    # Tester si Docker peut utiliser le GPU
    dc, dout, _ = _run(["docker", "info"], timeout=8)
    if dc == 0 and "nvidia" in dout.lower():
        return Dep("nvidia_container", "nvidia-container-toolkit", "ok",
                   "Docker GPU runtime actif", "nvidia-container-toolkit",
                   "NVIDIA Container Toolkit actif — GPU accessible dans les conteneurs Docker",
                   critical=False)

    # Vérifier le package directement
    pkg_checks = [
        ["dpkg", "-l", "nvidia-container-toolkit"],
        ["rpm", "-q", "nvidia-container-toolkit"],
        ["pacman", "-Q", "nvidia-container-toolkit"],
    ]
    for pkg_cmd in pkg_checks:
        code, out, _ = _run(pkg_cmd)
        if code == 0 and "nvidia" in out.lower():
            return Dep("nvidia_container", "nvidia-container-toolkit", "ok",
                       "installé", "nvidia-container-toolkit",
                       "NVIDIA Container Toolkit installé (restart Docker daemon pour activer)",
                       critical=False)

    return Dep("nvidia_container", "nvidia-container-toolkit", "missing",
               "non trouvé (GPU NVIDIA détecté)", "nvidia-container-toolkit",
               "GPU NVIDIA présent mais nvidia-container-toolkit absent. "
               "Sans lui, Docker ne peut pas accéder au GPU. "
               "Installer: bash installer/linux/bootstrap.sh",
               install_cmd="bash installer/linux/bootstrap.sh",
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
    """Windows only — vérifie WSL2 (pas WSL1)."""
    if not IS_WINDOWS:
        return Dep("wsl", "WSL2 (Windows uniquement)", "ok", "N/A — Linux natif",
                   "Requis sur Windows", "Environnement Linux natif détecté")
    code, out, err = _run(["wsl", "--status"], timeout=15)
    if code == 0 and out:
        # Vérifier spécifiquement WSL2
        combined = (out + err).lower()
        if "default version: 2" in combined or "version par défaut : 2" in combined:
            return Dep("wsl", "WSL2", "ok", "WSL2 (version par défaut)", "WSL2 + Ubuntu",
                       "Environnement Linux pour tous les services backend — WSL2 confirmé")
        if "version: 2" in combined or "wsl2" in combined:
            return Dep("wsl", "WSL2", "ok", "WSL2 actif", "WSL2 + Ubuntu",
                       "Environnement Linux pour tous les services backend")
        if "1" in combined:
            return Dep("wsl", "WSL2", "outdated", "WSL1 détecté", "WSL2 requis",
                       "WSL1 détecté — convertir en WSL2 pour les performances Docker: "
                       "wsl --set-default-version 2 && wsl --set-version Ubuntu 2",
                       install_cmd="wsl --set-default-version 2", critical=True)
        # WSL présent mais version incertaine — considérer comme OK sur Win11
        return Dep("wsl", "WSL2", "ok", "WSL actif (version non déterminée)", "WSL2",
                   "WSL actif — vérifiez manuellement avec: wsl --status")
    if code != 0:
        # Vérifier si WSL disponible mais pas de distro
        code2, out2, _ = _run(["wsl", "--list"], timeout=10)
        if code2 == 0:
            return Dep("wsl", "WSL2", "outdated", "WSL sans distribution Linux", "WSL2 + Ubuntu",
                       "WSL installé mais aucune distribution Ubuntu. "
                       "Installez Ubuntu: wsl --install Ubuntu",
                       install_cmd="wsl --install Ubuntu", critical=True)
    return Dep("wsl", "WSL2", "missing", "non détecté", "WSL2 + Ubuntu",
               "WSL2 est requis sur Windows pour exécuter les services Linux (Docker natif, backend, AI engine)",
               install_cmd="wsl --install (redémarrage requis)", critical=True)


def check_ports() -> list[Dep]:
    """Vérifie que les ports requis sont libres (aucun conflit avant installation)."""
    deps: list[Dep] = []
    blocked: list[str] = []
    for port, service in REQUIRED_PORTS.items():
        if not _port_free(port):
            blocked.append(f":{port} ({service})")

    if not blocked:
        deps.append(Dep("ports", "Ports réseau requis", "ok",
                        f"{len(REQUIRED_PORTS)} ports vérifiés", "ports libres",
                        "Tous les ports requis par CitéVision v2 sont disponibles",
                        critical=False))
    else:
        deps.append(Dep("ports", "Ports réseau requis", "error",
                        f"{len(blocked)} port(s) occupé(s)", "ports libres",
                        f"Ports en conflit: {', '.join(blocked[:5])}. "
                        "Libérez ces ports avant d'installer.",
                        install_cmd="Identifier le processus: netstat -tlnp | grep <port>",
                        critical=False))
    return deps


def check_postgres_connectivity() -> Dep:
    """Vérifie la connectivité PostgreSQL (port 5432 ou 5433) si Docker est up."""
    for port in (5433, 5432):
        if _port_in_use(port):
            return Dep("postgres_conn", f"PostgreSQL :{port}", "ok",
                       f"Port {port} répond", f":{port} accessible",
                       f"PostgreSQL écoute sur le port {port}", critical=False)
    return Dep("postgres_conn", "PostgreSQL (connectivité)", "missing",
               "ports 5432 et 5433 fermés", ":5432 ou :5433 accessible",
               "PostgreSQL n'est pas joignable. Démarrez docker compose up -d postgres",
               install_cmd="docker compose up -d postgres", critical=False)


def check_redis_connectivity() -> Dep:
    """Vérifie la connectivité Redis (port 6379 ou 6380) si Docker est up."""
    for port in (6380, 6379):
        if _port_in_use(port):
            return Dep("redis_conn", f"Redis :{port}", "ok",
                       f"Port {port} répond", f":{port} accessible",
                       f"Redis écoute sur le port {port}", critical=False)
    return Dep("redis_conn", "Redis (connectivité)", "missing",
               "ports 6379 et 6380 fermés", ":6379 ou :6380 accessible",
               "Redis n'est pas joignable. Démarrez docker compose up -d redis",
               install_cmd="docker compose up -d redis", critical=False)


def check_yolo_model() -> Dep:
    models_dir = ROOT / "ai-engine" / "models"
    # Vérifier le modèle recommandé par generated.env, sinon yolov8n.onnx
    gen_env = ROOT / "generated.env"
    cv_model = "yolov8n.onnx"
    if gen_env.exists():
        try:
            for line in gen_env.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("CV_YOLO_MODEL="):
                    cv_model = line.split("=", 1)[1].strip()
                    break
        except Exception:
            pass
    model_path = models_dir / cv_model
    fallback_path = models_dir / "yolov8n.onnx"

    if model_path.exists():
        size_mb = model_path.stat().st_size / 1024 / 1024
        return Dep("yolo_model", f"Modèle YOLO ({cv_model})", "ok",
                   f"{size_mb:.1f} Mo", "≥ 6 Mo",
                   f"Modèle de détection d'objets ({cv_model}) — prêt pour l'inférence vidéo")
    if cv_model != "yolov8n.onnx" and fallback_path.exists():
        size_mb = fallback_path.stat().st_size / 1024 / 1024
        return Dep("yolo_model", f"Modèle YOLO ({cv_model})", "outdated",
                   f"yolov8n.onnx présent ({size_mb:.1f} Mo)",
                   f"{cv_model} recommandé pour votre GPU",
                   f"Le modèle optimal pour votre GPU ({cv_model}) est absent — "
                   "yolov8n.onnx sera utilisé en fallback (performances réduites)",
                   install_cmd=f"YOLO_MODEL={cv_model} bash scripts/download-yolo-model.sh",
                   critical=False)
    return Dep("yolo_model", f"Modèle YOLO ({cv_model})", "missing",
               "non trouvé", f"{cv_model} (≈ 6–100 Mo selon tier GPU)",
               "Modèle de détection YOLO requis pour toute analyse vidéo et application des règles. "
               f"Attendu : {model_path}",
               install_cmd="bash scripts/download-yolo-model.sh",
               critical=True)


def check_frontend_deps() -> Dep:
    nm = ROOT / "frontend" / "node_modules"
    linux_rollup = nm / "@rollup" / "rollup-linux-x64-gnu"

    def _linux_rollup_ok() -> bool:
        if IS_WINDOWS:
            code, _, _ = _wsl_run(["test", "-d", _to_wsl_path(linux_rollup)], timeout=10)
            return code == 0
        return linux_rollup.exists()

    if nm.exists() and (nm / "react").exists() and _linux_rollup_ok():
        return Dep("frontend_deps", "Dépendances frontend (node_modules)", "ok",
                   "installées (Linux/WSL)", "npm install",
                   "React, Vite, TailwindCSS et toutes les librairies UI")
    if nm.exists() and (nm / "react").exists():
        return Dep("frontend_deps", "Dépendances frontend (node_modules)", "missing",
                   "incompatibles WSL (npm Windows détecté)", "npm install dans WSL",
                   "node_modules doit être installé sous Linux/WSL pour Vite (bindings Rollup natifs)",
                   install_cmd=f"wsl -- bash -c 'cd {_to_wsl_path(ROOT)} && source scripts/lib/env-utils.sh && ensure_frontend_deps .'")
    return Dep("frontend_deps", "Dépendances frontend (node_modules)", "missing",
               "non installées", "npm install",
               "Requis pour lancer ou builder le frontend React",
               install_cmd=f"wsl -- bash -c 'cd {_to_wsl_path(ROOT)} && source scripts/lib/env-utils.sh && ensure_frontend_deps .'")


def check_python_venv() -> Dep:
    venv = ROOT / "ai-engine" / ".venv"
    try:
        venv_exists = venv.exists()
        lib_exists = venv_exists and (venv / "lib").exists()
    except OSError:
        # WSL symlink not readable by Windows Python — venv lives on ext4, treat as ok
        venv_exists = True
        lib_exists = True
    if venv_exists:
        if lib_exists:
            return Dep("python_venv", "Virtualenv AI Engine (.venv)", "ok",
                       str(venv), "pip install -r requirements.txt",
                       "Environnement Python isolé pour l'AI engine")
    return Dep("python_venv", "Virtualenv AI Engine (.venv)", "missing",
               "non créé", "python3 -m venv + pip install",
               "Environnement Python isolé pour l'AI engine et ses dépendances ONNX",
               install_cmd="cd ai-engine && python3.12 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt")


def check_windows_startup() -> Dep:
    """Verifie la configuration demarrage Windows (Task Scheduler, sans services.msc)."""
    marker = ROOT / "installer" / ".startup_configured"
    mode = read_service_start_mode()
    rc, _, _ = _run(["schtasks", "/Query", "/TN", "CiteVision-AutoStart"], timeout=8)
    auto_task = rc == 0
    rc_wd, _, _ = _run(["schtasks", "/Query", "/TN", "CiteVision-Watchdog"], timeout=8)
    watchdog_task = rc_wd == 0

    if mode == "auto" and auto_task:
        detail = "taches planifiees actives (connexion + surveillance 3 min)"
        return Dep(
            "windows_startup",
            "Demarrage automatique Windows",
            "ok",
            detail,
            "start-citevision.bat pour demarrage manuel immediat",
            "CiteVision demarre a la connexion et se relance si un arret est detecte.",
            install_cmd=None,
            critical=False,
        )
    if marker.exists() or mode == "manual":
        return Dep(
            "windows_startup",
            "Demarrage automatique Windows",
            "ok" if marker.exists() else "outdated",
            f"mode manuel ({mode})",
            "start-citevision.bat",
            "Demarrage manuel via start-citevision.bat a la racine du projet.",
            install_cmd=None,
            critical=False,
        )
    start_bat = str(ROOT / "start-citevision.bat")
    return Dep(
        "windows_startup",
        "Demarrage automatique Windows",
        "missing",
        "non configure",
        "start-citevision.bat ou reinstaller",
        "Le demarrage automatique n'est pas encore configure — relancez l'installation ou start-citevision.bat.",
        install_cmd=start_bat,
        critical=False,
    )


# ---------------------------------------------------------------------------
# Run all checks
# ---------------------------------------------------------------------------
def run_all(mode: str = "check") -> dict:
    deps: list[Dep] = [
        check_python(),
        check_docker(),
        check_docker_running(),
        check_docker_group(),
        check_docker_compose(),
        check_go(),
        check_node(),
        check_npm(),
        check_ffmpeg(),
        check_git(),
        check_git_config(),
        check_cuda_toolkit(),
        check_nvidia_container(),
        check_jq(),
        check_cmake(),
        check_yolo_model(),
        check_frontend_deps(),
        check_python_venv(),
    ]
    if IS_WINDOWS:
        deps.insert(2, check_wsl())
        deps.append(check_windows_startup())

    # Port checks (retourne liste)
    deps.extend(check_ports())

    # Connectivity checks (seulement si Docker tourne)
    dc, _, _ = _run(["docker", "info"], timeout=5)
    if dc == 0:
        deps.append(check_postgres_connectivity())
        deps.append(check_redis_connectivity())

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
    s = win_path.as_posix()
    if len(s) >= 2 and s[1] == ":":
        drive = s[0].lower()
        rest = s[2:]
        return f"/mnt/{drive}{rest}"
    return s


def _win_path_exists(p: Path) -> bool:
    return p.exists()


# ---------------------------------------------------------------------------
# SSE install stream
# ---------------------------------------------------------------------------
def _parse_startup_ps1_output(out: str, err: str) -> tuple[bool, str]:
    """Parse JSON from install-startup.ps1 stdout (last JSON line wins)."""
    combined = (out or "") + "\n" + (err or "")
    for line in reversed(combined.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
            ok_key = "startup_ok" if "startup_ok" in data else "service_ok"
            if ok_key in data:
                ok = bool(data.get(ok_key))
                err_msg = data.get("error") or ""
                if ok:
                    mode = data.get("start_mode", "auto")
                    return True, f"Demarrage Windows configure (mode: {mode})"
                return False, err_msg or "Configuration demarrage Windows echouee"
        except json.JSONDecodeError:
            continue
    text = (out or err or "").strip()
    if text:
        return False, text[-500:]
    return False, "Configuration demarrage Windows echouee (pas de reponse)"


def _predownload_nssm() -> tuple[bool, str]:
    """Pre-download NSSM during install so Ouvrir CitéVision is faster."""
    if not IS_WINDOWS:
        return True, "skipped"
    nssm_exe = ROOT / "installer" / "windows" / "nssm.exe"
    if nssm_exe.exists():
        return True, "NSSM déjà présent"
    urls = [
        "https://nssm.cc/release/nssm-2.24.zip",
        "https://github.com/fawno/nssm.cc/releases/download/v2.24.1/nssm-v2.24.1-Win64.zip",
        "https://github.com/fawno/nssm.cc/releases/download/v2.24.1/nssm-v2.24.1-Win32.zip",
    ]
    url_list = ",".join(f"'{u}'" for u in urls)
    ps_cmd = (
        f"$nssm='{nssm_exe}'; "
        "if (Test-Path $nssm) { exit 0 }; "
        "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; "
        f"$urls=@({url_list}); "
        "$zip=Join-Path $env:TEMP 'nssm-download.zip'; "
        "$ext=Join-Path $env:TEMP 'nssm-extract'; "
        "foreach ($url in $urls) { "
        "  try { "
        "    if (Test-Path $zip) { Remove-Item -Force $zip }; "
        "    if (Test-Path $ext) { Remove-Item -Recurse -Force $ext }; "
        "    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing -TimeoutSec 90; "
        "    Expand-Archive -Path $zip -DestinationPath $ext -Force; "
        "    $bin=Get-ChildItem -Path $ext -Recurse -Filter nssm.exe | "
        "      Where-Object { $_.FullName -match 'win64' } | Select-Object -First 1; "
        "    if (-not $bin) { $bin=Get-ChildItem -Path $ext -Recurse -Filter nssm.exe | Select-Object -First 1 }; "
        "    if ($bin) { Copy-Item $bin.FullName $nssm -Force; exit 0 } "
        "  } catch {} "
        "}; exit 1"
    )
    rc, out, err = _run([
        "powershell", "-NoLogo", "-NonInteractive", "-NoProfile",
        "-ExecutionPolicy", "Bypass", "-Command", ps_cmd,
    ], timeout=120)
    if nssm_exe.exists():
        return True, "NSSM téléchargé"
    return False, (out or err or "NSSM non téléchargé").strip()[:200]


def _read_service_result_file() -> dict | None:
    """Read JSON written by install-service.ps1 (Emit-Result)."""
    import os
    path = Path(os.environ.get("TEMP", "C:/Windows/Temp")) / "citevision-svc-result.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _service_account_status() -> str:
    """Return 'ok', 'bad_account', or 'missing'."""
    rc, out, _ = _run(["sc", "qc", WINDOWS_SERVICE_NAME], timeout=10)
    if rc != 0:
        return "missing"
    for line in out.splitlines():
        if "SERVICE_START_NAME" in line:
            account = line.split(":", 1)[-1].strip().lower()
            bad = ("localsystem", "local service", "networkservice",
                   "nt authority\\localservice", "nt authority\\networkservice")
            if account in bad or not account:
                return "bad_account"
            return "ok"
    return "missing"


def _windows_service_account_ok() -> bool:
    return _service_account_status() == "ok"


def _read_register_log_tail(max_chars: int = 800) -> str:
    parts: list[str] = []
    for name in ("register-service-install.log", "register-service.log"):
        log_path = ROOT / "logs" / name
        if not log_path.exists():
            continue
        try:
            parts.append(log_path.read_text(encoding="utf-8", errors="replace")[-max_chars:])
        except OSError:
            pass
    return "\n".join(parts).strip()[-max_chars:]


def _configure_windows_startup(start_mode: str) -> tuple[bool, str]:
    """Configure demarrage Windows via Task Scheduler (sans services.msc)."""
    ps1 = ROOT / "installer" / "windows" / "install-startup.ps1"
    if not ps1.exists():
        return False, f"Script introuvable : {ps1}"
    mode_file = ROOT / "installer" / ".service_start_mode"
    try:
        mode_file.parent.mkdir(parents=True, exist_ok=True)
        mode_file.write_text(start_mode if start_mode in ("auto", "manual") else "auto", encoding="utf-8")
    except OSError as e:
        return False, f"Impossible d'écrire le mode de démarrage : {e}"

    import os
    result_path = Path(os.environ.get("TEMP", "C:/Windows/Temp")) / "citevision-startup-result.json"
    try:
        result_path.unlink(missing_ok=True)
    except OSError:
        pass

    rc, out, err = _run([
        "powershell", "-NoLogo", "-NonInteractive", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(ps1), "-StartMode", start_mode, "-Root", str(ROOT.resolve()),
        "-ResultFile", str(result_path),
    ], timeout=120)

    if result_path.exists():
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
            if data.get("startup_ok") or data.get("service_ok"):
                mode = data.get("start_mode", start_mode)
                return True, f"Demarrage Windows configure (mode: {mode})"
            if data.get("error"):
                return False, str(data["error"])
        except (OSError, json.JSONDecodeError):
            pass

    ok, msg = _parse_startup_ps1_output(out, err)
    if ok:
        return True, msg
    if rc != 0:
        return False, msg or f"Configuration demarrage echouee (code {rc})"
    return False, msg or "Configuration demarrage Windows echouee"


def windows_startup_status() -> dict:
    """Etat demarrage Windows pour l'installateur."""
    if not IS_WINDOWS:
        return {"configured": False, "mode": "skipped", "auto_task": False}
    mode = read_service_start_mode()
    marker = (ROOT / "installer" / ".startup_configured").exists()
    rc, _, _ = _run(["schtasks", "/Query", "/TN", "CiteVision-AutoStart"], timeout=8)
    auto_task = rc == 0
    return {
        "configured": marker or auto_task,
        "mode": mode,
        "auto_task": auto_task,
        "registered": marker or auto_task,  # compat
    }


def read_service_start_mode() -> str:
    """Lit le mode de démarrage (marqueur install-startup prioritaire)."""
    marker_mode = _read_start_mode_from_marker()
    if marker_mode:
        return marker_mode
    mode_file = ROOT / "installer" / ".service_start_mode"
    if mode_file.exists():
        try:
            mode = _strip_bom(mode_file.read_text(encoding="utf-8").strip())
            if "|" in mode:
                mode = mode.split("|", 1)[0].strip()
            if mode in ("auto", "manual"):
                return mode
        except OSError:
            pass
    return "auto"


def _strip_bom(text: str) -> str:
    return text.lstrip("\ufeff")


def _read_start_mode_from_marker() -> str:
    marker_path = ROOT / "installer" / ".startup_configured"
    if not marker_path.exists():
        return ""
    try:
        mode = _strip_bom(marker_path.read_text(encoding="utf-8").split("|", 1)[0].strip())
        if mode in ("auto", "manual"):
            return mode
    except OSError:
        pass
    return ""


def write_service_start_mode(mode: str) -> None:
    """Persiste le mode via Python (fiable sur NTFS, même quand WSL echo échoue)."""
    if mode not in ("auto", "manual"):
        raise ValueError(f"invalid start mode: {mode}")
    mode_file = ROOT / "installer" / ".service_start_mode"
    mode_file.parent.mkdir(parents=True, exist_ok=True)
    mode_file.write_text(mode, encoding="utf-8", newline="")
    if mode_file.read_text(encoding="utf-8").strip() != mode:
        raise OSError(f"write verify failed for {mode_file}")


def write_startup_marker(mode: str, mechanism: str = "configured") -> None:
    marker = ROOT / "installer" / ".startup_configured"
    marker.parent.mkdir(parents=True, exist_ok=True)
    value = f"{mode}|{mechanism}"
    marker.write_text(value, encoding="utf-8", newline="")
    if _strip_bom(marker.read_text(encoding="utf-8").split("|", 1)[0].strip()) != mode:
        raise OSError(f"write verify failed for {marker}")


def ensure_project_root_env() -> None:
    """Aligne PROJECT_ROOT dans .env sur l'arborescence d'installation réelle."""
    env_file = ROOT / ".env"
    wsl_root = _to_wsl_path(ROOT.resolve()) if IS_WINDOWS else str(ROOT.resolve())
    lines: list[str] = []
    found = False
    if env_file.exists():
        try:
            lines = env_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
    out: list[str] = []
    for line in lines:
        if line.startswith("PROJECT_ROOT="):
            out.append(f"PROJECT_ROOT={wsl_root}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"PROJECT_ROOT={wsl_root}")
    try:
        env_file.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    except OSError:
        pass


def _read_internal_api_key() -> str:
    env_file = ROOT / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("INTERNAL_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val
        except OSError:
            pass
    return os.environ.get("INTERNAL_API_KEY", "changeme_internal_service_key")


def _windows_auto_task_exists() -> bool:
    rc, _, _ = _run(["schtasks", "/Query", "/TN", "CiteVision-AutoStart"], timeout=8)
    return rc == 0


def _windows_registry_autostart() -> bool:
    rc, out, _ = _run([
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        "(Get-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run' "
        "-Name 'CiteVision' -ErrorAction SilentlyContinue).CiteVision",
    ], timeout=12)
    return rc == 0 and bool((out or "").strip())


def _windows_startup_link_exists() -> bool:
    rc, out, _ = _run([
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        "$s=[Environment]::GetFolderPath('Startup'); "
        "if($s){Test-Path (Join-Path $s 'CiteVision.lnk')}else{$false}",
    ], timeout=12)
    return rc == 0 and (out or "").strip().lower() == "true"


def _sync_start_mode_to_backend(mode: str) -> tuple[bool | None, str]:
    """Applique le mode via l'API interne si le backend tourne déjà (réinstall sur stack active)."""
    try:
        key = _read_internal_api_key()
        payload = json.dumps({"mode": mode}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8081/api/v1/internal/system/apply-start-mode",
            data=payload,
            headers={
                "X-Internal-Key": key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            ok = bool(data.get("ok"))
            verify = data.get("verify") or {}
            msg = verify.get("message") or data.get("message") or ("sync ok" if ok else "sync failed")
            return ok, str(msg)
    except urllib.error.URLError:
        return None, "backend non joignable"
    except Exception as e:
        return False, str(e)


def verify_start_mode_config(expected: str) -> dict:
    """Vérification bout-en-bout : fichier, marqueur Windows, OS, backend Paramètres."""
    actual = read_service_start_mode()
    file_ok = actual == expected
    marker_path = ROOT / "installer" / ".startup_configured"
    marker_mode = _read_start_mode_from_marker()
    marker_ok = marker_path.exists()
    marker_match = marker_ok and marker_mode == expected
    os_ok = True
    os_detail = ""
    if IS_WINDOWS:
        auto_task = _windows_auto_task_exists()
        reg_run = _windows_registry_autostart()
        startup_link = _windows_startup_link_exists()
        auto_active = auto_task or reg_run or startup_link
        if expected == "auto":
            os_ok = auto_active or marker_ok
            os_detail = "autostart_active" if auto_active else "marker_only"
        else:
            os_ok = not auto_active
            os_detail = "no_autostart" if not auto_active else "autostart_still_active"
    backend_ok: bool | None = None
    backend_detail = ""
    try:
        key = _read_internal_api_key()
        url = (
            "http://127.0.0.1:8081/api/v1/internal/system/verify-start-mode"
            f"?expected={urllib.parse.quote(expected)}"
        )
        req = urllib.request.Request(url, headers={"X-Internal-Key": key})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            backend_ok = bool(data.get("ok"))
            backend_detail = (
                f"api={data.get('start_mode')}/{data.get('start_mode_effective')}"
                f" root={data.get('project_root', '')}"
            )
    except Exception:
        backend_ok = None
        backend_detail = "backend_offline"
    all_ok = file_ok and marker_match and os_ok
    if backend_ok is not None:
        all_ok = all_ok and backend_ok
    return {
        "all_ok": all_ok,
        "expected": expected,
        "file_mode": actual,
        "file_ok": file_ok,
        "marker_ok": marker_match,
        "marker_mode": marker_mode,
        "os_ok": os_ok,
        "os_detail": os_detail,
        "backend_ok": backend_ok,
        "backend_detail": backend_detail,
    }


def apply_install_start_mode(mode: str) -> tuple[bool, str, dict]:
    """
    Applique le mode choisi à l'installation : fichier, .env, mécanismes OS, sync backend.
    Ne stoppe pas la stack en cours.
    """
    if mode not in ("auto", "manual"):
        mode = "auto"
    write_service_start_mode(mode)
    ensure_project_root_env()
    svc = register_system_service(mode)
    # Double persistance Python (NTFS) — install-startup.ps1 peut loguer OK sans écrire le fichier.
    try:
        write_service_start_mode(mode)
        mech = "manual" if mode == "manual" else "windows-startup"
        if svc.get("ok"):
            mech = str(svc.get("message", mech))[:120]
        write_startup_marker(mode, mech)
    except OSError as exc:
        return False, f"Persistance mode échouée après configuration OS : {exc}", {
            "all_ok": False,
            "expected": mode,
            "file_mode": read_service_start_mode(),
        }
    sync_ok, sync_msg = _sync_start_mode_to_backend(mode)
    verify = verify_start_mode_config(mode)
    if sync_ok is not None:
        verify["backend_sync"] = sync_ok
        verify["backend_sync_detail"] = sync_msg
        if not sync_ok:
            verify["all_ok"] = False
    ok = bool(svc.get("ok")) and bool(verify.get("all_ok"))
    msg = svc.get("message", "")
    if not verify.get("all_ok"):
        parts = []
        if not verify.get("file_ok"):
            parts.append(f"fichier={verify.get('file_mode')}")
        if not verify.get("marker_ok"):
            parts.append(f"marqueur={verify.get('marker_mode') or 'absent'}")
        if not verify.get("os_ok"):
            parts.append(f"os={verify.get('os_detail')}")
        if verify.get("backend_ok") is False:
            parts.append(verify.get("backend_detail", "backend"))
        msg = "Vérification mode démarrage échouée: " + ", ".join(parts)
    elif sync_msg and sync_ok:
        msg = f"{msg} — {sync_msg}".strip(" —")
    return ok, msg, verify


def _register_linux_service(start_mode: str) -> tuple[bool, str]:
    """Enregistre citevision.service via systemd (Linux natif)."""
    script = ROOT / "installer" / "linux" / "install-service.sh"
    if not script.exists():
        return False, f"Script introuvable : {script}"
    import getpass
    user = getpass.getuser()
    rc, out, err = _run([
        "sudo", "bash", str(script),
        f"--root={ROOT}", f"--user={user}", f"--start-mode={start_mode}",
    ], timeout=120)
    msg = (out or err or "").strip()
    if rc == 0:
        for line in reversed(msg.splitlines()):
            line = line.strip()
            if line.startswith("{") and "service_ok" in line:
                try:
                    data = json.loads(line)
                    if data.get("service_ok"):
                        return True, f"Service citevision.service enregistré (mode: {start_mode})"
                except json.JSONDecodeError:
                    pass
        return True, msg or f"Service citevision.service enregistré (mode: {start_mode})"
    if "password" in msg.lower() or "sudo" in msg.lower():
        return False, "sudo requis — exécutez: sudo bash installer/linux/install-service.sh"
    return False, msg or f"Enregistrement service Linux échoué (code {rc})"


def register_system_service(start_mode: str | None = None) -> dict:
    """
    Enregistre le demarrage systeme CitéVision (Windows Task Scheduler ou Linux systemd).
    Retourne {"ok": bool, "message": str, "start_mode": str, "skipped": bool}.
    """
    import shutil

    mode = start_mode if start_mode in ("auto", "manual") else read_service_start_mode()
    if IS_WINDOWS:
        ok, msg = _configure_windows_startup(mode)
        return {"ok": ok, "message": msg, "start_mode": mode, "skipped": False, "platform": "windows"}
    if not shutil.which("systemctl"):
        return {
            "ok": True,
            "message": "systemd non disponible — service non enregistré (démarrage manuel via scripts/start-linux.sh)",
            "start_mode": mode,
            "skipped": True,
            "platform": "linux",
        }
    ok, msg = _register_linux_service(mode)
    return {"ok": ok, "message": msg, "start_mode": mode, "skipped": False, "platform": "linux"}


def install_stream(start_mode: str = "auto"):
    """
    Générateur SSE : installe les dépendances manquantes via setup-wsl.sh.
    Sur Windows, le script est exécuté via WSL avec la conversion de chemin.
    """
    if start_mode not in ("auto", "manual"):
        start_mode = "auto"

    def emit(event: str, **kw) -> str:
        return f"data: {json.dumps({'event': event, **kw}, ensure_ascii=False)}\n\n"

    yield emit("step", message="Démarrage de l'installation CitéVision v2…")
    mode_label = "automatique" if start_mode == "auto" else "manuel"
    yield emit("info", message=f"Mode de démarrage du service : {mode_label}")

    try:
        write_service_start_mode(start_mode)
        ensure_project_root_env()
        if read_service_start_mode() != start_mode:
            yield emit("error", message="Échec persistance immédiate du mode de démarrage")
            return
        yield emit("ok", message=f"Mode {mode_label} enregistré (fichier + PROJECT_ROOT)")
    except Exception as e:
        yield emit("error", message=f"Impossible d'enregistrer le mode de démarrage : {e}")
        return

    setup_script = ROOT / "scripts" / "setup-wsl.sh"
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "installer.log"

    if not setup_script.exists():
        yield emit("error", message=f"Script introuvable : {setup_script}")
        return

    popen_kwargs: dict = dict(
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        stdin=subprocess.DEVNULL,
    )

    if IS_WINDOWS:
        yield emit("step", message="Démarrage de l'installation automatique…")
        wsl_script = _to_wsl_path(setup_script)
        wsl_log = _to_wsl_path(log_file)
        cmd = [
            "wsl", "--",
            "bash", wsl_script,
            "--silent",
            f"--log-file={wsl_log}",
            f"--start-mode={start_mode}",
        ]
        # log_dir already created above via Path.mkdir(); skip WSL mkdir to avoid timeout
        popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        popen_kwargs["text"] = True
        popen_kwargs["encoding"] = "utf-8"
        popen_kwargs["errors"] = "replace"
    else:
        yield emit("step", message="Démarrage de l'installation Linux…")
        cmd = [
            "bash", str(setup_script), "--silent",
            f"--log-file={log_file}", f"--start-mode={start_mode}",
        ]
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
        except Exception:
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
            yield emit("heartbeat", message=heartbeat_msgs[hb_idx % len(heartbeat_msgs)])
            hb_idx += 1
            continue

        if kind == "done":
            rc = payload
            if rc == 0:
                yield emit("step", message="Application et vérification du mode de démarrage…")
                try:
                    sm_ok, sm_msg, sm_verify = apply_install_start_mode(start_mode)
                    if sm_ok:
                        yield emit(
                            "ok",
                            message=(
                                f"Mode {mode_label} synchronisé — fichier, marqueur, OS"
                                + (
                                    " et Paramètres"
                                    if sm_verify.get("backend_ok")
                                    else " (backend hors ligne — vérifié au prochain démarrage)"
                                )
                            ),
                        )
                    else:
                        yield emit("error", message=sm_msg or "Mode de démarrage non synchronisé")
                        return
                except Exception as e:
                    yield emit("error", message=f"Configuration démarrage échouée : {e}")
                    return

                yield emit("step", message="Validation post-install AI stack…")
                try:
                    import importlib.util
                    af_spec = importlib.util.spec_from_file_location(
                        "auto_fix", ROOT / "installer" / "auto-fix.py"
                    )
                    af = importlib.util.module_from_spec(af_spec)
                    af_spec.loader.exec_module(af)
                    install_ok = True
                    for evt in af.ensure_install_stack_stream(max_rounds=5):
                        ev = evt.get("event", "info")
                        msg = evt.get("message", "")
                        yield emit(ev, message=msg)
                        if ev == "error":
                            install_ok = False
                            break
                    if install_ok:
                        yield emit("done", message="Installation terminée avec succès !")
                    else:
                        yield emit(
                            "warn",
                            message="Installation — mode démarrage OK ; AI stack non validé après auto-fix",
                        )
                        yield emit("done", message="Installation terminée (mode démarrage validé, IA à corriger)")
                except Exception as e:
                    import traceback
                    yield emit(
                        "warn",
                        message=f"Validation post-install IA échouée (mode démarrage déjà appliqué) : {e}",
                    )
                    yield emit("done", message="Installation terminée (mode démarrage validé)")
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
            line = payload
            if not line:
                continue
            low = line.lower()
            if "[err]" in low or "error" in low or "failed" in low:
                evt = "error"
            elif "[fix]" in low:
                evt = "fix"
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
    """SSE generator: runs start-linux.sh via WSL then verifies all services are healthy."""
    def emit(event: str, **kw) -> str:
        return f"data: {json.dumps({'event': event, **kw}, ensure_ascii=False)}\n\n"

    start_script = ROOT / "scripts" / "start-linux.sh"
    if not start_script.exists():
        yield emit("error", message=f"Script introuvable : {start_script}")
        return

    yield emit("step", message="Démarrage des services CitéVision...")

    import queue as _queue, threading as _threading, time as _time
    import urllib.request as _urlreq

    def _poll_port(port: int, timeout: int = 120) -> bool:
        import socket as _socket
        deadline = _time.time() + timeout
        while _time.time() < deadline:
            try:
                with _socket.create_connection(("localhost", port), timeout=2):
                    return True
            except Exception:
                _time.sleep(3)
        return False

    def _poll_http_key(url: str, key: str, expected: str, timeout: int = 60) -> bool:
        """Poll a JSON endpoint until response[key] == expected."""
        import json as _json
        deadline = _time.time() + timeout
        while _time.time() < deadline:
            try:
                with _urlreq.urlopen(url, timeout=3) as r:
                    data = _json.loads(r.read())
                    if str(data.get(key, "")).lower() == expected.lower():
                        return True
            except Exception:
                pass
            _time.sleep(3)
        return False

    def _poll_all_ai_models(url: str, timeout: int = 180) -> tuple[bool, str]:
        """Poll /health until all registry keys are true (honest gate)."""
        import json as _json
        labels = {
            "yolo_loaded": "YOLO",
            "face_loaded": "InsightFace",
            "plate_loaded": "PaddleOCR",
            "yolo_cuda": "CUDA GPU",
            "driver_phone_model_loaded": "Téléphone (ONNX)",
            "seatbelt_model_loaded": "Ceinture (ONNX)",
        }
        require_keys = list(labels.keys())
        deadline = _time.time() + timeout
        missing: list[str] = list(labels.values())
        while _time.time() < deadline:
            try:
                with _urlreq.urlopen(url, timeout=3) as r:
                    data = _json.loads(r.read())
                missing = [
                    labels[key] for key in require_keys
                    if str(data.get(key, "")).lower() != "true"
                ]
                if not missing:
                    return True, ""
            except Exception:
                missing = list(labels.values())
            _time.sleep(3)
        return False, ", ".join(missing)

    def _resolve_app_url(base: str = "http://localhost:5174", timeout: int = 15) -> str:
        """Return /setup or /login based on backend setup status."""
        import json as _json
        origin = base.rstrip("/")
        deadline = _time.time() + timeout
        while _time.time() < deadline:
            try:
                with _urlreq.urlopen("http://localhost:8081/api/v1/setup/status", timeout=3) as r:
                    data = _json.loads(r.read())
                    if data.get("initialized"):
                        return f"{origin}/login"
                    return f"{origin}/setup"
            except Exception:
                pass
            _time.sleep(2)
        return f"{origin}/setup"

    line_q: _queue.Queue = _queue.Queue()

    def _run() -> None:
        try:
            wsl_script = _to_wsl_path(start_script)
            kwargs: dict = dict(
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                bufsize=1, stdin=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="replace",
            )
            if IS_WINDOWS:
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
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
        "Démarrage Docker Engine natif (WSL)…",
        "Installation / démarrage dockerd si nécessaire…",
        "Démarrage du backend Go...",
        "Compilation des modules Go (premier démarrage)...",
        "Téléchargement / vérification du modèle YOLO...",
        "Démarrage de l'AI engine...",
        "Téléchargement InsightFace (buffalo_l)...",
        "Initialisation PaddleOCR...",
        "Chargement du modèle YOLO (initialisation ONNX)...",
        "Démarrage du moteur de règles...",
        "Démarrage du frontend Vite...",
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
                # ── Vérification séquentielle de tous les services ──────────
                yield emit("step", message="Vérification du backend (8081)...")
                if _poll_port(8081, timeout=30):
                    yield emit("ok", message="Backend API opérationnel")
                else:
                    yield emit("warn", message="Backend lent — vérifiez logs/backend.log")

                yield emit("step", message="Vérification de l'AI Engine (8001)...")
                ai_up = _poll_port(8001, timeout=120)
                af = None
                try:
                    import importlib.util
                    af_spec = importlib.util.spec_from_file_location(
                        "auto_fix", ROOT / "installer" / "auto-fix.py"
                    )
                    af = importlib.util.module_from_spec(af_spec)
                    af_spec.loader.exec_module(af)
                    if ai_up:
                        yield emit("ok", message="AI Engine démarré — correction automatique si nécessaire…")
                    else:
                        yield emit("fix", message="AI Engine non joignable — correction automatique…")
                    for evt in af.ensure_launch_ai_stream(max_rounds=8):
                        ev = evt.get("event", "info")
                        msg = evt.get("message", "")
                        yield emit(ev, message=msg)
                except Exception as e:
                    import traceback
                    yield emit("ai_fail", message=f"Auto-fix IA échoué : {e}")

                yield emit("step", message="Vérification du moteur de règles (8010)...")
                if _poll_port(8010, timeout=30):
                    yield emit("ok", message="Moteur de règles opérationnel")
                else:
                    yield emit("warn", message="Moteur de règles non joignable — vérifiez logs/rules-engine.log")

                yield emit("step", message="Vérification de l'interface (5174)...")
                app_url = _resolve_app_url()
                if not _poll_port(5174, timeout=120):
                    yield emit("fix", message="Interface non joignable — réinstallation des dépendances frontend (WSL)…")
                    try:
                        wsl_root = _to_wsl_path(ROOT)
                        fix_cmd = [
                            "wsl", "--", "bash", "-lc",
                            f"cd '{wsl_root}' && source scripts/lib/env-utils.sh && "
                            "ensure_frontend_deps . && "
                            "stop_from_pid logs/frontend.pid 2>/dev/null || true; "
                            "free_port 5174; "
                            f"start_bg frontend '{wsl_root}/frontend' "
                            "'npm run dev -- --host 0.0.0.0 --port 5174 --strictPort' logs .env",
                        ]
                        subprocess.run(
                            fix_cmd, cwd=str(ROOT), timeout=600, check=False,
                            creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
                        )
                    except Exception as e:
                        yield emit("warn", message=f"Auto-fix frontend échoué : {e}")
                if _poll_port(5174, timeout=90):
                    yield emit("ok", message="Interface CitéVision accessible")
                    # Gate IA obligatoire avant launch_ready (YOLO + InsightFace + PaddleOCR)
                    while True:
                        gate_ok, missing = _poll_all_ai_models(
                            "http://localhost:8001/health", timeout=15
                        )
                        if gate_ok:
                            yield emit(
                                "ai_ready",
                                message="AI Engine opérationnel — registre IA complet (YOLO, InsightFace, PaddleOCR, secondaires, CUDA)",
                            )
                            break
                        miss_txt = missing or "modèles IA"
                        yield emit(
                            "fix",
                            message=f"Gate IA — correction automatique ({miss_txt})…",
                        )
                        try:
                            if af is None:
                                import importlib.util
                                af_spec = importlib.util.spec_from_file_location(
                                    "auto_fix_gate", ROOT / "installer" / "auto-fix.py"
                                )
                                af = importlib.util.module_from_spec(af_spec)
                                af_spec.loader.exec_module(af)
                            for evt in af.ensure_launch_ai_stream(max_rounds=1):
                                ev = evt.get("event", "fix")
                                msg = evt.get("message", "")
                                if ev == "ai_ready":
                                    gate_ok = True
                                yield emit(ev, message=msg)
                            if gate_ok:
                                break
                        except Exception:
                            pass
                        _time.sleep(3)
                    yield emit("launch_ready", message=app_url)
                else:
                    yield emit("error", message="Interface non démarrée sur le port 5174 — consultez logs/frontend.log")
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
            if "[fix]" in low:
                evt = "fix"
            elif "[ok]" in low or "healthy" in low or "ready" in low:
                if "gate ia" in low or (
                    "yolo" in low and "insightface" in low and "paddleocr" in low
                ):
                    evt = "ai_ready"
                else:
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
