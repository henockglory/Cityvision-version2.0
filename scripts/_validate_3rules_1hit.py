#!/usr/bin/env python3
"""Infra once + diagnostic + 3× validation 1-hit (Python unique, pas de tour 30 min)."""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs" / "validate-3rules-1hit.log"

RULES = (
    "Démo · Feu rouge",
    "Démo · Excès de vitesse",
    "Démo · Téléphone au volant",
)


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def run(cmd: list[str], *, check: bool = True) -> int:
    log(f"$ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if r.stdout:
        sys.stdout.write(r.stdout)
    if r.stderr:
        sys.stderr.write(r.stderr)
    if check and r.returncode != 0:
        raise SystemExit(r.returncode)
    return r.returncode


def health(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def bootstrap_infra() -> None:
    log("=== Infra (once) ===")
    run(["bash", "scripts/_restart_backend.sh"])
    run(["docker", "restart", "citevision-v2-go2rtc", "citevision-v2-frigate"], check=False)
    time.sleep(20)
    run(["python3", "scripts/_restart_ai.py"])
    run(["bash", "scripts/_restart_backend.sh"], check=False)
    time.sleep(5)
    if not health("http://127.0.0.1:8001/health"):
        log("FAIL AI health after bootstrap")
        raise SystemExit(1)
    if not health("http://127.0.0.1:8081/health"):
        log("FAIL backend health after bootstrap")
        raise SystemExit(1)


def main() -> int:
    LOG.write_text("", encoding="utf-8")
    os.chdir(ROOT)
    bootstrap_infra()

    log("=== Diagnostic preuve (event sans alerte) ===")
    subprocess.run([sys.executable, "scripts/_diag_suppressed_evidence.py"], cwd=ROOT, check=False)

    passed = 0
    failed = 0
    for rule in RULES:
        log(f"=== 1-hit: {rule} ===")
        env = {**os.environ, "RULE_NAME": rule}
        r = subprocess.run(
            [sys.executable, "-u", "scripts/_validate_rule_frigate_1hit.py"],
            cwd=ROOT, env=env,
        )
        if r.returncode == 0:
            passed += 1
        else:
            failed += 1
        time.sleep(15)

    log(f"=== SUMMARY pass={passed} fail={failed} ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
