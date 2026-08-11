#!/usr/bin/env python3
"""Export CiteVision-Overview.pdf from overview HTML (print CSS, all rules open)."""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from build_overview import build_html  # noqa: E402

PDF_NAME = "CiteVision-Overview.pdf"
TMP_HTML = ROOT / "_overview_pdf_source.html"


def find_browser() -> Path:
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(shutil.which("chrome") or ""),
        Path(shutil.which("msedge") or ""),
    ]
    for p in candidates:
        if p and p.is_file():
            return p
    raise SystemExit("Chrome/Edge not found — cannot print PDF")


def main() -> None:
    # Rebuild screen HTML + print source (all <details open>)
    screen = ROOT / "overview.html"
    screen.write_text(build_html(open_all=False), encoding="utf-8", newline="\n")
    TMP_HTML.write_text(build_html(open_all=True), encoding="utf-8", newline="\n")

    browser = find_browser()
    out_pdf = ROOT / PDF_NAME
    if out_pdf.exists():
        out_pdf.unlink()

    # file:// URL — forward slashes required
    url = TMP_HTML.resolve().as_uri()
    cmd = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--hide-scrollbars",
        "--virtual-time-budget=15000",
        "--run-all-compositor-stages-before-draw",
        "--no-pdf-header-footer",
        "--no-margins",
        f"--print-to-pdf={out_pdf}",
        url,
    ]
    print("Running:", browser.name, "->", out_pdf.name)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    # Chromium sometimes writes PDF then exits non-zero; wait briefly for FS
    for _ in range(40):
        if out_pdf.is_file() and out_pdf.stat().st_size > 50_000:
            break
        time.sleep(0.25)
    else:
        sys.stderr.write(proc.stdout or "")
        sys.stderr.write(proc.stderr or "")
        raise SystemExit(
            f"PDF not produced (exit={proc.returncode}, size="
            f"{out_pdf.stat().st_size if out_pdf.exists() else 0})"
        )

    TMP_HTML.unlink(missing_ok=True)
    print(f"Wrote {out_pdf} ({out_pdf.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
