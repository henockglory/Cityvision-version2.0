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
  GET  /api/version           → commit build + racine projet
  GET  /static/*              → fichiers statiques de installer/ui/
"""
from __future__ import annotations

import importlib.util
import json
import os
import platform
import secrets
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

# One-time setup token: gates the powerful install/launch/service endpoints so
# only the browser the installer itself opened (which receives the token via a
# SameSite cookie) can trigger them. Prevents other local users/processes on a
# shared machine from driving the installer.
SETUP_TOKEN = secrets.token_urlsafe(24)
UI_DIR_RESOLVED = UI_DIR.resolve()


def _resolve_within(base: Path, rel: str):
    """Resolve rel under base, returning the path only if it stays inside base.
    Defends against path traversal (../) in static asset requests."""
    try:
        candidate = (base / rel.lstrip("/")).resolve()
    except (OSError, ValueError):
        return None
    if candidate == base or base in candidate.parents:
        return candidate
    return None


def _cookie_token(handler: BaseHTTPRequestHandler) -> str:
    raw = handler.headers.get("Cookie", "") or ""
    for part in raw.split(";"):
        kv = part.strip().split("=", 1)
        if len(kv) == 2 and kv[0] == "cv_setup":
            return kv[1]
    return ""


def _authorized(handler: BaseHTTPRequestHandler) -> bool:
    """Sensitive endpoints require the setup token (cookie or query param)."""
    if _cookie_token(handler) == SETUP_TOKEN:
        return True
    qs = parse_qs(urlparse(handler.path).query)
    return qs.get("token", [""])[0] == SETUP_TOKEN


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
    # The installer is loopback-only and same-origin; echo the Origin only when
    # it is a localhost origin instead of the permissive wildcard.
    origin = handler.headers.get("Origin", "") or ""
    host = urlparse(origin).hostname if origin else None
    if host in ("localhost", "127.0.0.1"):
        handler.send_header("Access-Control-Allow-Origin", origin)
        handler.send_header("Access-Control-Allow-Credentials", "true")
    handler.send_header("Vary", "Origin")
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
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
    if getattr(handler, "_set_setup_cookie", False):
        handler.send_header(
            "Set-Cookie",
            f"cv_setup={SETUP_TOKEN}; Path=/; SameSite=Strict; Max-Age=3600",
        )
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

        # Root → index.html (also hands the browser the one-time setup token)
        if path in ("/", "/index.html"):
            self._set_setup_cookie = True
            _serve_file(self, UI_DIR / "index.html")
            return

        # Premium loading page (opened in the new tab while CitéVision boots)
        if path in ("/loading", "/loading.html"):
            _serve_file(self, UI_DIR / "loading.html")
            return

        # Static assets (path-traversal safe)
        if path.startswith("/static/"):
            asset = path[len("/static/"):]
            target = _resolve_within(UI_DIR_RESOLVED, asset)
            if target is None:
                self.send_response(403)
                self.end_headers()
                return
            _serve_file(self, target)
            return

        # Serve CSS/JS directly from / (path-traversal safe)
        for ext in (".css", ".js", ".svg", ".png", ".ico", ".woff2"):
            if path.endswith(ext):
                target = _resolve_within(UI_DIR_RESOLVED, path.lstrip("/"))
                if target is None:
                    self.send_response(403)
                    self.end_headers()
                    return
                _serve_file(self, target)
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

        if path == "/api/version":
            commit = "unknown"
            build_file = INSTALLER_DIR / ".build_version"
            if build_file.is_file():
                lines = build_file.read_text(encoding="utf-8").strip().splitlines()
                if lines:
                    commit = lines[0].strip()
            else:
                try:
                    r = _subprocess.run(
                        ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                        capture_output=True, text=True, timeout=5,
                    )
                    if r.returncode == 0 and r.stdout.strip():
                        commit = r.stdout.strip()
                except Exception:
                    pass
            _send_json(self, {"commit": commit, "root": str(ROOT)})
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

        if path == "/api/service-status":
            try:
                dc = _load_module("deps_checker", INSTALLER_DIR / "deps-checker.py")
                _send_json(self, dc.windows_service_registration_status())
            except Exception as e:
                _send_json(self, {"registered": False, "status": "error", "message": str(e)})
            return

        if path == "/api/register-service" or path.startswith("/api/register-service?"):
            if not _authorized(self):
                _send_json(self, {"ok": False, "message": "unauthorized"}, status=403)
                return
            try:
                dc = _load_module("deps_checker", INSTALLER_DIR / "deps-checker.py")
                result = dc.register_system_service()
                _send_json(self, result)
            except Exception as e:
                import traceback
                _send_json(self, {"ok": False, "message": traceback.format_exc(), "skipped": False})
            return

        if path == "/api/launch":
            if not _authorized(self):
                _send_json(self, {"error": "unauthorized"}, status=403)
                return
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
            if not _authorized(self):
                _send_json(self, {"error": "unauthorized"}, status=403)
                return
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
            s.bind(("127.0.0.1", port))
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


def _warn_stale_install_dir():
    """Warn if a legacy accented C:\\CitéVision folder coexists with the
    canonical ASCII C:\\Citevision, to avoid confusion between the two."""
    if platform.system() != "Windows":
        return
    canonical = Path("C:/Citevision")
    legacy = Path("C:/Cit\u00e9Vision")  # C:\CitéVision
    try:
        if legacy.exists() and str(legacy).lower() != str(ROOT).lower():
            print("")
            print("  [!] Dossier hérité détecté : C:\\CitéVision (avec accent)")
            print("      Le dossier officiel est désormais C:\\Citevision (sans accent).")
            print("      Après vérification, vous pouvez supprimer l'ancien C:\\CitéVision")
            print("      pour éviter toute confusion.")
            print("=" * 60)
    except OSError:
        pass


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

    # Bind to loopback only: the installer never needs to be reachable from the
    # network, and several endpoints can install software / register services.
    server = ThreadedHTTPServer(("127.0.0.1", PORT), InstallerHandler)
    url = f"http://localhost:{PORT}"

    print("=" * 60)
    print("  CitéVision v2 — Assistant d'installation")
    print("=" * 60)
    print(f"  Interface : {url}")
    print(f"  Ouverture du navigateur dans 1.5s…")
    print("  Ctrl+C pour arrêter")
    print("=" * 60)
    _warn_stale_install_dir()

    open_browser_delayed(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[CitéVision Installer] Arrêt du serveur.")
        server.server_close()


if __name__ == "__main__":
    main()
