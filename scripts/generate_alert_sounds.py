#!/usr/bin/env python3
"""Generate short, loud alert WAV files for CiteVision (stdlib only)."""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 44100
AMP = 0.85  # strong but avoid hard clip after envelope

OUT = Path(__file__).resolve().parents[1] / "frontend" / "public" / "sounds" / "alerts"


def _env(i: int, n: int, attack: float = 0.01, release: float = 0.05) -> float:
    t = i / SAMPLE_RATE
    dur = n / SAMPLE_RATE
    a = min(1.0, t / attack) if attack > 0 else 1.0
    r = 1.0
    if release > 0 and t > dur - release:
        r = max(0.0, (dur - t) / release)
    return a * r


def _tone(freq: float, duration: float, wave_fn="sine") -> list[float]:
    n = max(1, int(SAMPLE_RATE * duration))
    out: list[float] = []
    for i in range(n):
        t = i / SAMPLE_RATE
        phase = 2 * math.pi * freq * t
        if wave_fn == "square":
            s = 1.0 if math.sin(phase) >= 0 else -1.0
        elif wave_fn == "saw":
            s = 2.0 * ((freq * t) % 1.0) - 1.0
        elif wave_fn == "triangle":
            s = 2.0 * abs(2.0 * ((freq * t) % 1.0) - 1.0) - 1.0
        else:
            s = math.sin(phase)
        out.append(s * AMP * _env(i, n))
    return out


def _chirp(f0: float, f1: float, duration: float) -> list[float]:
    n = max(1, int(SAMPLE_RATE * duration))
    out: list[float] = []
    for i in range(n):
        t = i / SAMPLE_RATE
        frac = t / duration if duration > 0 else 0
        freq = f0 + (f1 - f0) * frac
        phase = 2 * math.pi * freq * t
        out.append(math.sin(phase) * AMP * _env(i, n, 0.008, 0.04))
    return out


def _silence(duration: float) -> list[float]:
    return [0.0] * max(1, int(SAMPLE_RATE * duration))


def _join(*parts: list[float]) -> list[float]:
    acc: list[float] = []
    for p in parts:
        acc.extend(p)
    return acc


def write_wav(path: Path, samples: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        frames = bytearray()
        for s in samples:
            v = max(-1.0, min(1.0, s))
            frames += struct.pack("<h", int(v * 32767))
        w.writeframes(frames)


SOUNDS: dict[str, list[float]] = {
    "pulse_hi": _tone(880, 0.22, "square"),
    "pulse_mid": _tone(660, 0.25, "square"),
    "pulse_lo": _tone(440, 0.28, "square"),
    "double_beep": _join(_tone(980, 0.12, "square"), _silence(0.06), _tone(980, 0.12, "square")),
    "triple_beep": _join(
        _tone(1040, 0.08, "square"),
        _silence(0.04),
        _tone(1040, 0.08, "square"),
        _silence(0.04),
        _tone(1040, 0.08, "square"),
    ),
    "siren_up": _chirp(500, 1200, 0.45),
    "siren_down": _chirp(1200, 500, 0.45),
    "siren_sweep": _join(_chirp(600, 1100, 0.22), _chirp(1100, 600, 0.22)),
    "klaxon": _join(_tone(420, 0.18, "saw"), _silence(0.05), _tone(420, 0.18, "saw")),
    "horn_blast": _tone(380, 0.35, "saw"),
    "alarm_a": _join(_tone(800, 0.1, "square"), _tone(600, 0.1, "square"), _tone(800, 0.1, "square")),
    "alarm_b": _join(_tone(700, 0.12, "triangle"), _silence(0.05), _tone(900, 0.12, "triangle")),
    "urgent_staccato": _join(
        *sum(([_tone(1100, 0.05, "square"), _silence(0.04)] for _ in range(5)), [])
    ),
    "sonar_ping": _chirp(1400, 400, 0.35),
    "buzz_alert": _tone(220, 0.4, "square"),
    "two_tone": _join(_tone(740, 0.16, "square"), _tone(980, 0.16, "square")),
    "three_tone": _join(_tone(620, 0.1, "square"), _tone(780, 0.1, "square"), _tone(980, 0.12, "square")),
    "impact": _join(_chirp(1800, 200, 0.12), _tone(160, 0.15, "sine")),
    "radar_blip": _join(_tone(1500, 0.06, "sine"), _silence(0.08), _tone(1500, 0.06, "sine")),
    "critical_burst": _join(
        _tone(1200, 0.08, "square"),
        _silence(0.03),
        _tone(900, 0.08, "square"),
        _silence(0.03),
        _tone(1400, 0.15, "square"),
    ),
    "gate_chime": _join(_tone(880, 0.1, "triangle"), _tone(1320, 0.14, "triangle")),
    "perimeter": _join(_tone(520, 0.2, "saw"), _silence(0.04), _tone(780, 0.2, "saw")),
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, samples in SOUNDS.items():
        path = OUT / f"{name}.wav"
        write_wav(path, samples)
        print(f"wrote {path} ({len(samples) / SAMPLE_RATE:.3f}s)")
    print(f"done: {len(SOUNDS)} sounds -> {OUT}")


if __name__ == "__main__":
    main()
