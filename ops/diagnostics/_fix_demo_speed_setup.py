"""
Trigger a demo heal PATCH to reconfigure the pipeline (reset ghost tracks, analytics state).
"""
import urllib.request, json, time

BASE = "http://127.0.0.1:8081"
AI   = "http://127.0.0.1:8001"
ORG  = "74d51ead-97a7-4e41-a488-503a9b90c466"

# --- Login ---
body = {"email": "glory.henock@hologram.cd", "password": "Henockglory@03"}
data = json.dumps(body).encode()
req = urllib.request.Request(f"{BASE}/api/v1/auth/login", data=data,
                             headers={"Content-Type": "application/json"}, method="POST")
result = json.loads(urllib.request.urlopen(req, timeout=10).read())
token = result["access_token"]
print("Token OK")

hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# --- Get demo settings ---
ds_req = urllib.request.Request(f"{BASE}/api/v1/orgs/{ORG}/demo/settings", headers=hdrs)
ds = json.loads(urllib.request.urlopen(ds_req, timeout=10).read())
print("Demo settings (abridged):", json.dumps({k: v for k, v in ds.items() if k in
      ["camera_id", "video_id", "pipeline_status", "is_active", "active_camera_id", "active_video_id"]}, indent=2))

# --- Trigger PATCH to restart demo pipeline ---
patch_data = json.dumps({}).encode()
patch_req = urllib.request.Request(
    f"{BASE}/api/v1/orgs/{ORG}/demo/settings",
    data=patch_data,
    headers=hdrs,
    method="PATCH"
)
try:
    patch_resp = json.loads(urllib.request.urlopen(patch_req, timeout=30).read())
    print("PATCH OK:", json.dumps(patch_resp)[:200])
except urllib.error.HTTPError as e:
    print("PATCH error:", e.code, e.read().decode()[:200])

print("Waiting 10s for heal...")
time.sleep(10)

# --- Check AI cameras ---
cam_req = urllib.request.Request(f"{AI}/cameras", method="GET")
cams = json.loads(urllib.request.urlopen(cam_req, timeout=10).read())
for c in cams.get("cameras", []):
    print(f"Camera {c['camera_id'][:8]}: frames={c['frames_processed']} published={c['frames_published']}")
