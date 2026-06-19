#!/usr/bin/env python3
"""
CitéVision v2 — Installer Setup Server
Serveur HTTP stdlib (aucun pip requis) — port 7315.
Sert l'UI d'installation et expose les APIs de vérification/installation.

Routes :
  GET  /                      → installer/ui/index.html
  GET  /api/hardware          → check-hardware.py (JSON)
  GET  /api/hardware-profile  → apply-hardware-profile.py --json (profil GPU + generated.env)
  GET  /api/deps              → deps-checker.py (JSON)
  POST /api/install           → SSE stream d'installation
  GET  /api/status            → état global de préparation
  GET  /api/app-status        → vérifie si l'app est déjà démarrée
  GET  /static/*              → fichiers statiques de installer/ui/
"""
from __future__ import annotations

import importlib.util
import json
import os
import platform
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = 7315
INSTALLER_DIR = Path(__file__).resolve().parent
UI_DIR = INSTALLER_DIR / "ui"
ROOT = INSTALLER_DIR.parent
APP_URL = "http://localhost:5174"


import subprocess as _subprocess


def _run_py_module(script: Path, timeout: int = 20, fallback: dict | None = None) -> dict:
    """Run a Python script as an isolated subprocess and parse its JSON stdout.
    Completely avoids blocking the HTTP server thread."""
    flags = {}
    if platform.system() == "Windows":
        flags["creationflags"] = _subprocess.CREATE_NO_WINDOW
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        r = _subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            stdin=_subprocess.DEVNULL,
            env=env,
            **flags,
        )
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout)
        err = r.stderr.strip() or r.stdout.strip() or f"exit {r.returncode}"
        return {**(fallback or {}), "error": err}
    except _subprocess.TimeoutExpired:
        return {**(fallback or {}), "error": f"Timeout après {timeout}s"}
    except Exception as exc:
        import traceback
        return {**(fallback or {}), "error": traceback.format_exc()}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore
    sys.modules[name] = mod  # required for @dataclass to resolve __module__
    try:
        spec.loader.exec_module(mod)  # type: ignore
    except Exception:
        sys.modules.pop(name, None)
        raise
    return mod


def _cors_headers(handler: BaseHTTPRequestHandler):
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")


def _send_json(handler: BaseHTTPRequestHandler, data: dict, status: int = 200):
    body = json.dumps(data, ensure_ascii=False).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    _cors_headers(handler)
    handler.end_headers()
    handler.wfile.write(body)


def _send_sse_stream(handler: BaseHTTPRequestHandler, gen):
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("X-Accel-Buffering", "no")
    _cors_headers(handler)
    handler.end_headers()
    try:
        for chunk in gen:
            if isinstance(chunk, str):
                handler.wfile.write(chunk.encode())
            else:
                handler.wfile.write(chunk)
            handler.wfile.flush()
    except BrokenPipeError:
        pass


def _serve_file(handler: BaseHTTPRequestHandler, path: Path):
    if not path.exists():
        handler.send_response(404)
        handler.end_headers()
        return
    mime = {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".ico": "image/x-icon",
        ".json": "application/json; charset=utf-8",
        ".woff2": "font/woff2",
    }.get(path.suffix, "application/octet-stream")
    body = path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", mime)
    handler.send_header("Content-Length", str(len(body)))
    _cors_headers(handler)
    handler.end_headers()
    handler.wfile.write(body)


class InstallerHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # silence default logging
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        _cors_headers(self)
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]

        # Root → index.html
        if path in ("/", "/index.html"):
            _serve_file(self, UI_DIR / "index.html")
            return

        # Static assets
        if path.startswith("/static/"):
            asset = path[len("/static/"):]
            _serve_file(self, UI_DIR / asset)
            return

        # Serve CSS/JS directly from /
        for ext in (".css", ".js", ".svg", ".png", ".ico", ".woff2"):
            if path.endswith(ext):
                _serve_file(self, UI_DIR / path.lstrip("/"))
                return

        if path == "/api/hardware":
            result = _run_py_module(INSTALLER_DIR / "check-hardware.py",
                                    fallback={"overall": "fail", "summary": "Timeout — relancez le diagnostic",
                                              "checks": [], "gpu_tier": {}})
            _send_json(self, result)
            return

        if path == "/api/deps":
            result = _run_py_module(INSTALLER_DIR / "deps-checker.py",
                                    fallback={"ready": False, "summary": "Timeout", "deps": []})
            _send_json(self, result)
            return

        if path == "/api/status":
            try:
                hw = _load_module("check_hardware", INSTALLER_DIR / "check-hardware.py")
                hw_res = hw.run_all()
                dc = _load_module("deps_checker", INSTALLER_DIR / "deps-checker.py")
                deps_res = dc.run_all()
                hw_ok = hw_res.get("overall") != "fail"
                deps_ok = deps_res.get("ready", False)
                _send_json(self, {
                    "hardware_ok": hw_ok,
                    "deps_ok": deps_ok,
                    "ready": hw_ok and deps_ok,
                    "gpu_tier": hw_res.get("gpu_tier", {}),
                })
            except Exception as e:
                _send_json(self, {"ready": False, "error": str(e)})
            return

        if path == "/api/hardware-profile":
            # Call apply-hardware-profile.py with --json flag for JSON output
            flags = {}
            if platform.system() == "Windows":
                flags["creationflags"] = _subprocess.CREATE_NO_WINDOW
            try:
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                r = _subprocess.run(
                    [sys.executable, str(INSTALLER_DIR / "apply-hardware-profile.py"), "--json"],
                    capture_output=True, text=True, encoding="utf-8",
                    timeout=35, stdin=_subprocess.DEVNULL, env=env, **flags,
                )
                if r.returncode == 0 and r.stdout.strip():
                    result = json.loads(r.stdout)
                else:
                    result = {"tier": "unknown", "error": r.stderr.strip() or f"exit {r.returncode}"}
            except _subprocess.TimeoutExpired:
                result = {"tier": "unknown", "error": "Timeout (35s) — relancez le diagnostic"}
            except Exception as exc:
                import traceback
                result = {"tier": "unknown", "error": traceback.format_exc()}
            _send_json(self, result)
            return

        if path == "/api/app-status":
            # Check if the main app is already running
            app_running = False
            try:
                urllib.request.urlopen("http://localhost:8081/health", timeout=2)
                app_running = True
            except Exception:
                pass
            _send_json(self, {"running": app_running, "url": APP_URL})
            return

        if path == "/api/register-service" or path.startswith("/api/register-service?"):
            try:
                dc = _load_module("deps_checker", INSTALLER_DIR / "deps-checker.py")
                result = dc.register_system_service()
                _send_json(self, result)
            except Exception as e:
                import traceback
                _send_json(self, {"ok": False, "message": traceback.format_exc(), "skipped": False})
            return

        if path == "/api/launch":
            try:
                dc = _load_module("deps_checker", INSTALLER_DIR / "deps-checker.py")
                _send_sse_stream(self, dc.launch_stream())
            except Exception as e:
                import traceback
                _send_sse_stream(self, iter([
                    f"data: {json.dumps({'event': 'error', 'message': traceback.format_exc()})}\n\n"
                ]))
            return

        # SSE install stream — EventSource only supports GET
        if path == "/api/install" or path.startswith("/api/install?"):
            try:
                parsed = urlparse(self.path)
                qs = parse_qs(parsed.query)
                start_mode = qs.get("start_mode", ["auto"])[0]
                if start_mode not in ("auto", "manual"):
                    start_mode = "auto"
                dc = _load_module("deps_checker", INSTALLER_DIR / "deps-checker.py")
                _send_sse_stream(self, dc.install_stream(start_mode=start_mode))
            except Exception as e:
                import traceback
                _send_sse_stream(self, iter([
                    f"data: {json.dumps({'event': 'error', 'message': traceback.format_exc()})}\n\n"
                ]))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        # Keep POST for backward compat
        self.do_GET()


def is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("", port))
            return True
        except OSError:
            return False


def open_browser_delayed(url: str, delay: float = 1.5):
    def _open():
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass
    threading.Thread(target=_open, daemon=True).start()


def main():
    global PORT
    if not is_port_free(PORT):
        # Try to see if our server is already running
        try:
            urllib.request.urlopen(f"http://localhost:{PORT}/api/status", timeout=2)
            print(f"[CitéVision Installer] Serveur déjà actif sur http://localhost:{PORT}")
            webbrowser.open(f"http://localhost:{PORT}")
            return
        except Exception:
            PORT += 1

    class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True

    server = ThreadedHTTPServer(("", PORT), InstallerHandler)
    url = f"http://localhost:{PORT}"

    print("=" * 60)
    print("  CitéVision v2 — Assistant d'installation")
    print("=" * 60)
    print(f"  Interface : {url}")
    print(f"  Ouverture du navigateur dans 1.5s…")
    print("  Ctrl+C pour arrêter")
    print("=" * 60)

    open_browser_delayed(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[CitéVision Installer] Arrêt du serveur.")
        server.server_close()


if __name__ == "__main__":
    main()
