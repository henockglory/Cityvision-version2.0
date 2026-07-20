import json, urllib.request
url = "http://127.0.0.1:8001/cameras/d2eb7076-c3b3-40fd-9b2c-0d119bb975c9/detections/latest"
with urllib.request.urlopen(url, timeout=15) as r:
    d = json.load(r)
print("detections", len(d.get("detections", [])), "overlay", len(d.get("overlay_detections", [])), "mode", d.get("pipeline_mode"))
