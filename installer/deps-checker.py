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
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

Status = Literal["ok", "missing", "outdated", "installing", "error"]

ROOT = Path(__file__).resolve().parent.parent
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

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


def check_docker_running() -> Dep:
    """Vérifie que le daemon Docker est actif, pas juste installé."""
    code, out, err = _run(["docker", "info"], timeout=8)
    if code == 0:
        # Extraire version du daemon
        ver_line = next((l for l in out.splitlines() if "Server Version" in l), "")
        ver = ver_line.split(":")[-1].strip() if ver_line else "actif"
        return Dep("docker_daemon", "Docker Daemon (actif)", "ok", ver, "daemon actif",
                   "Le daemon Docker répond correctement")
    # Docker non installé → pas critique ici (docker check couvre ça)
    if shutil.which("docker") is None:
        return Dep("docker_daemon", "Docker Daemon (actif)", "missing", "non installé",
                   "daemon actif", "Docker n'est pas installé",
                   install_cmd="curl -fsSL https://get.docker.com | sh", critical=False)
    return Dep("docker_daemon", "Docker Daemon (actif)", "error", "non démarré",
               "daemon actif",
               "Docker est installé mais le daemon n'est pas actif. "
               "Lancez: sudo systemctl start docker  (ou sudo service docker start)",
               install_cmd="sudo systemctl start docker", critical=True)


def check_docker_group() -> Dep:
    """Vérifie que l'utilisateur courant est dans le groupe docker (Linux/WSL)."""
    if IS_WINDOWS:
        # Dans WSL, vérifier via wsl
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
    code, out, _ = _run(["docker", "compose", "version"])
    if code == 0 and out:
        return Dep("docker_compose", "Docker Compose v2", "ok", out, "≥ 2.0",
                   "Orchestration des services infrastructure")
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
        wsl_log_dir = _to_wsl_path(log_dir)
        cmd = [
            "wsl", "--",
            "bash", wsl_script,
            "--silent",
            f"--log-file={wsl_log}",
        ]
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
        yield emit("step", message="Démarrage de l'installation Linux…")
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
        "Démarrage du backend Go...",
        "Compilation des modules Go (premier démarrage)...",
        "Téléchargement / vérification du modèle YOLO...",
        "Démarrage de l'AI engine...",
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
                ai_yolo_ok = False
                if ai_up:
                    yield emit("ok", message="AI Engine démarré — vérification modèle YOLO...")
                    ai_yolo_ok = _poll_http_key(
                        "http://localhost:8001/health", "yolo_loaded", "true", timeout=60
                    )
                    if ai_yolo_ok:
                        yield emit("ok", message="AI Engine opérationnel — modèle YOLO chargé")
                    else:
                        yield emit("warn", message=(
                            "AI Engine up mais YOLO non chargé — "
                            "détection vidéo non disponible. "
                            "Lancez : bash scripts/download-yolo-model.sh"
                        ))
                else:
                    yield emit("warn", message=(
                        "AI Engine non joignable après 120s — "
                        "surveillance IA désactivée. "
                        "Vérifiez logs/ai-engine.log"
                    ))

                yield emit("step", message="Vérification du moteur de règles (8010)...")
                if _poll_port(8010, timeout=30):
                    yield emit("ok", message="Moteur de règles opérationnel")
                else:
                    yield emit("warn", message="Moteur de règles non joignable — vérifiez logs/rules-engine.log")

                yield emit("step", message="Vérification de l'interface (5174)...")
                if _poll_port(5174, timeout=60):
                    yield emit("ok", message="Interface CitéVision accessible")
                    if not ai_yolo_ok:
                        yield emit("warn", message=(
                            "L'IA sera disponible dans quelques instants — "
                            "actualisez System Health dans l'application"
                        ))
                    yield emit("launch_ready", message="http://localhost:5174")
                else:
                    yield emit("warn", message="Timeout interface — tentez d'ouvrir manuellement")
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
