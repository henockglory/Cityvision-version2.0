#!/usr/bin/env python3
"""Galerie cabine — TOUS les crops Frigate envoyés à Gemini (YES et NO)."""
from __future__ import annotations

import html
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(os.environ.get("MICROTEST_ROOT", Path.home() / "citevision-v2"))
TS = os.environ.get("HIT1_TS") or os.environ.get("VLM_CABIN_RUN") or os.environ.get("TS") or ""
MIN_CROPS = max(1, int(os.environ.get("CABIN_MIN_CROPS", "1") or 1))


def main() -> int:
    if not TS:
        print("HIT1_TS or VLM_CABIN_RUN required", flush=True)
        return 2

    dump_dir = Path(os.environ.get("VLM_CABIN_DUMP_DIR") or "")
    if not dump_dir or not dump_dir.is_dir():
        dump_dir = ROOT / "validation-evidence" / f"vlm-cabin-{TS}"
    out_wsl = ROOT / "validation-evidence" / f"1hit-cabin-{TS}"
    out_win = Path(r"C:\Users\gheno\citevision") / "validation-evidence" / f"1hit-cabin-{TS}"
    out_wsl.mkdir(parents=True, exist_ok=True)

    index_path = dump_dir / "index.jsonl"
    items: list[dict] = []
    if index_path.is_file():
        for line in index_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    else:
        # Fallback: reconstruct from *_verdict.json
        for p in sorted(dump_dir.glob("*_verdict.json")):
            try:
                items.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue

    cards: list[dict] = []
    yes_n = no_n = err_n = 0
    for idx, it in enumerate(items, 1):
        outcome = str(it.get("outcome") or ("yes" if it.get("violation") else "no"))
        if outcome == "yes":
            yes_n += 1
        elif outcome == "no":
            no_n += 1
        else:
            err_n += 1
        crop_name = str(it.get("crop_file") or "")
        prompt_name = str(it.get("prompt_file") or "")
        folder = out_wsl / f"call_{idx:03d}_{outcome}_{str(it.get('rule') or 'rule')[:20]}"
        folder.mkdir(parents=True, exist_ok=True)
        media: dict[str, str] = {}
        src_crop = dump_dir / crop_name if crop_name else None
        if src_crop and src_crop.is_file():
            dest = folder / "crop.jpg"
            dest.write_bytes(src_crop.read_bytes())
            media["crop"] = str(dest.relative_to(out_wsl)).replace("\\", "/")
        prompt_txt = ""
        src_prompt = dump_dir / prompt_name if prompt_name else None
        if src_prompt and src_prompt.is_file():
            prompt_txt = src_prompt.read_text(encoding="utf-8")
            (folder / "prompt.txt").write_text(prompt_txt, encoding="utf-8")
        (folder / "verdict.json").write_text(
            json.dumps(it, indent=2, ensure_ascii=False), encoding="utf-8",
        )
        process_ok = bool(media.get("crop") and prompt_txt and "violation" in it)
        cards.append({
            "folder": folder.name,
            "media": media,
            "meta": {**it, "prompt_text": prompt_txt, "process_ok": process_ok},
        })
        print(
            f"  call#{idx} rule={it.get('rule')} outcome={outcome} "
            f"conf={it.get('confidence')} crop={bool(media.get('crop'))}",
            flush=True,
        )

    process_pass = (
        len(cards) >= MIN_CROPS
        and all((c.get("meta") or {}).get("process_ok") for c in cards)
        and any((c.get("meta") or {}).get("process_ok") for c in cards)
    )
    summary = {
        "ts": TS,
        "dump_dir": str(dump_dir),
        "calls": len(cards),
        "yes": yes_n,
        "no": no_n,
        "error": err_n,
        "min_crops": MIN_CROPS,
        "overall_pass": process_pass,
        "note": "PASS = process (crops+prompts Gemini visibles), pas forcément une alerte YES",
        "items": [
            {
                "folder": c["folder"],
                "rule": (c.get("meta") or {}).get("rule"),
                "outcome": (c.get("meta") or {}).get("outcome"),
                "process_ok": (c.get("meta") or {}).get("process_ok"),
            }
            for c in cards
        ],
    }
    (out_wsl / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    banner = (
        f"PASS — {len(cards)} crop(s) Frigate→Gemini visibles (yes={yes_n} no={no_n})"
        if process_pass
        else f"FAIL — crops insuffisants ou incomplets (calls={len(cards)} min={MIN_CROPS})"
    )
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>1-hit cabine Gemini — {html.escape(TS)}</title>",
        "<style>",
        "body{font-family:Segoe UI,system-ui,sans-serif;margin:24px;background:#0f1115;color:#e8eaed}",
        ".banner{padding:14px 18px;border-radius:10px;margin:0 0 20px;font-weight:600}",
        ".ok{background:#1e3a2f;color:#8fd9a8}.bad{background:#3a1e1e;color:#f28b82}",
        ".yes{background:#3a2e1e;color:#f5c16c}.no{background:#1e2a3a;color:#8ab4f8}",
        ".card{border:1px solid #2a2f3a;border-radius:12px;padding:16px;margin:0 0 24px;background:#171a21}",
        ".grid{display:grid;grid-template-columns:320px 1fr;gap:16px}",
        "img{max-width:100%;border-radius:8px;border:1px solid #333}",
        "pre{white-space:pre-wrap;background:#0c0e12;padding:12px;border-radius:8px;font-size:12px;max-height:320px;overflow:auto}",
        ".tag{display:inline-block;padding:2px 8px;border-radius:999px;background:#2a3140;margin:0 6px 6px 0;font-size:12px}",
        "@media(max-width:800px){.grid{grid-template-columns:1fr}}",
        "</style></head><body>",
        f"<h1>Ceinture + téléphone — crops Gemini (oui ET non) — {html.escape(TS)}</h1>",
        f"<div class='banner {'ok' if process_pass else 'bad'}'>{html.escape(banner)}</div>",
        f"<p>dump={html.escape(str(dump_dir))} · yes={yes_n} no={no_n} error={err_n}</p>",
        "<p>Chaque carte = JPEG exact envoyé à Gemini + prompt + verdict JSON. "
        "Les NON sont volontairement inclus (contrairement à demo5 vide).</p>",
    ]
    for c in cards:
        m = c.get("meta") or {}
        media = c.get("media") or {}
        outcome = str(m.get("outcome") or "")
        oc = "yes" if outcome == "yes" else ("no" if outcome == "no" else "bad")
        parts.append("<div class='card'>")
        parts.append(
            f"<h2>{html.escape(str(m.get('rule') or ''))} "
            f"<span class='tag {oc}'>{html.escape(outcome.upper())}</span> "
            f"<span class='tag'>conf={html.escape(str(m.get('confidence')))}</span></h2>"
        )
        parts.append(
            f"<span class='tag'>frigate_event={html.escape(str(m.get('frigate_event_id') or '')[:20])}</span>"
            f"<span class='tag'>zone={html.escape(str(m.get('zone_id') or ''))}</span>"
        )
        reason = str(m.get("reason_short") or "")
        if reason:
            parts.append(f"<p>{html.escape(reason)}</p>")
        parts.append("<div class='grid'>")
        if media.get("crop"):
            parts.append(
                f"<div><div class='tag'>Frigate vehicle_bbox crop → Gemini</div>"
                f"<img src='{html.escape(media['crop'])}' alt='crop'></div>"
            )
        else:
            parts.append("<div class='tag bad'>MISSING CROP</div>")
        prompt = str(m.get("prompt_text") or "")
        parts.append(
            "<div><div class='tag'>prompt.txt</div>"
            f"<pre>{html.escape(prompt)}</pre>"
            "<div class='tag'>verdict.json</div>"
            f"<pre>{html.escape(json.dumps({k: m.get(k) for k in ('rule','outcome','violation','confidence','reason_short','error','bbox')}, indent=2, ensure_ascii=False))}</pre>"
            "</div>"
        )
        parts.append("</div></div>")
    parts.append("</body></html>")
    (out_wsl / "index.html").write_text("\n".join(parts), encoding="utf-8")

    try:
        out_win.parent.mkdir(parents=True, exist_ok=True)
        if out_win.exists():
            shutil.rmtree(out_win, ignore_errors=True)
        shutil.copytree(out_wsl, out_win)
    except Exception as exc:
        print(f"win copy warn: {exc}", flush=True)

    print(f"OVERALL_PASS={process_pass}", flush=True)
    print(f"CALLS={len(cards)} YES={yes_n} NO={no_n}", flush=True)
    print(f"GALLERY={out_wsl / 'index.html'}", flush=True)
    print(f"GALLERY_WIN={out_win / 'index.html'}", flush=True)
    return 0 if process_pass else 1


if __name__ == "__main__":
    sys.exit(main())
