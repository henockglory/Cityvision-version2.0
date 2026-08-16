#!/usr/bin/env python3
"""Frigate MQTT detect gate — boost one camera without leaving retained OFF state.

Temporary boost uses retain=False. restore_all / clear_retained_detect clear
ghost retained detect/set messages from older protocole-2 runs.
"""
from __future__ import annotations

import json
import time
import urllib.request
from typing import Iterable


FRIGATE_URL = "http://127.0.0.1:5000"
MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1884


def _mqtt_client():
    import paho.mqtt.client as mqtt  # type: ignore

    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except Exception:
        return mqtt.Client()


def cv_name(camera_id: str) -> str:
    s = str(camera_id)
    return s if s.startswith("cv_") else f"cv_{s}"


def list_frigate_cameras(frigate_url: str = FRIGATE_URL) -> list[str]:
    with urllib.request.urlopen(f"{frigate_url}/api/stats", timeout=10) as resp:
        stats = json.loads(resp.read().decode())
    return list((stats.get("cameras") or {}).keys())


def publish_detect(
    camera_ids: Iterable[str],
    *,
    on: bool,
    retain: bool = False,
    mqtt_host: str = MQTT_HOST,
    mqtt_port: int = MQTT_PORT,
    kinds: Iterable[str] = ("detect",),
) -> None:
    """Publish detect/set (and optionally enabled/set) for the given cameras.

    kinds=("enabled", "detect") fully wakes/stops a camera: detect OFF alone
    keeps ffmpeg decoding (12 demo cams pinned Frigate at ~676% CPU).
    """
    payload = "ON" if on else "OFF"
    cli = _mqtt_client()
    cli.connect(mqtt_host, mqtt_port, 60)
    cli.loop_start()
    time.sleep(0.25)
    for cid in camera_ids:
        name = cv_name(cid)
        for kind in kinds:
            topic = f"frigate/{name}/{kind}/set"
            cli.publish(topic, payload, qos=1, retain=retain)
            print(
                f"  [frigate-gate] {kind} {payload} retain={int(retain)} {name[-24:]}",
                flush=True,
            )
    time.sleep(0.6)
    cli.loop_stop()
    cli.disconnect()


def clear_retained_detect(
    camera_ids: Iterable[str] | None = None,
    *,
    mqtt_host: str = MQTT_HOST,
    mqtt_port: int = MQTT_PORT,
    frigate_url: str = FRIGATE_URL,
    publish_state: bool | None = False,
) -> list[str]:
    """Clear retained detect/set ghosts, then optionally publish a uniform state.

    publish_state=False (default) aligns with the compiler contract: detect is
    ON only for cameras with enabled rules; rule activation re-boosts its cam.
    publish_state=None only clears retained (Frigate keeps config defaults).
    """
    notes: list[str] = []
    cams = list(camera_ids) if camera_ids is not None else list_frigate_cameras(frigate_url)
    if not cams:
        return ["no_cameras"]
    cli = _mqtt_client()
    cli.connect(mqtt_host, mqtt_port, 60)
    cli.loop_start()
    time.sleep(0.25)
    state = "" if publish_state is None else ("ON" if publish_state else "OFF")
    for cid in cams:
        name = cv_name(cid)
        for kind in ("detect", "enabled"):
            topic = f"frigate/{name}/{kind}/set"
            # Empty retained payload clears Mosquitto retained message.
            cli.publish(topic, b"", qos=1, retain=True)
            if state:
                cli.publish(topic, state, qos=1, retain=False)
        print(f"  [frigate-gate] clear+{state or 'config'} {name[-24:]}", flush=True)
    time.sleep(0.8)
    cli.loop_stop()
    cli.disconnect()
    notes.append(f"cleared_retained={len(cams)} state={state or 'config'}")
    return notes


def boost(
    keep_camera_id: str,
    *,
    frigate_url: str = FRIGATE_URL,
) -> list[str]:
    """Detect OFF on all other cams (no retain); ON on keep (no retain)."""
    notes: list[str] = []
    cams: list[str] = []
    last_err: Exception | None = None
    for _ in range(8):
        try:
            cams = list_frigate_cameras(frigate_url)
            last_err = None
            break
        except Exception as e:
            last_err = e
            time.sleep(2)
    if last_err is not None and not cams:
        return [f"frigate_stats:{last_err}"]
    keep = cv_name(keep_camera_id)
    others = [c for c in cams if c != keep]
    if others:
        # enabled OFF stops ffmpeg decode entirely — detect OFF alone is not
        # enough to free Frigate CPU for the active camera.
        publish_detect(others, on=False, retain=False, kinds=("detect", "enabled"))
        notes.append(f"detect_off={len(others)}")
    publish_detect([keep], on=True, retain=False, kinds=("enabled", "detect"))
    notes.append("detect_on_keep")
    return notes


def restore_all(*, frigate_url: str = FRIGATE_URL, on: bool = False) -> list[str]:
    """Reset detect to idle. Default OFF everywhere: forcing ON on 12 demo cams
    pinned Frigate at ~676% CPU between runs and starved the active rule."""
    try:
        cams = list_frigate_cameras(frigate_url)
    except Exception as e:
        return [f"frigate_stats:{e}"]
    if not cams:
        return ["no_cameras"]
    kinds = ("enabled", "detect") if on else ("detect", "enabled")
    publish_detect(cams, on=on, retain=False, kinds=kinds)
    return [f"detect_{'on' if on else 'off'}_all={len(cams)}"]
