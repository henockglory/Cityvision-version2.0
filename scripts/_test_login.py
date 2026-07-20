import urllib.request, json, sys

BASE = "http://127.0.0.1:8081"
body = {"email": "glory.henock@hologram.cd", "password": "Henockglory@03"}
data = json.dumps(body).encode()
req = urllib.request.Request(
    f"{BASE}/api/v1/auth/login",
    data=data,
    headers={"Content-Type": "application/json"},
    method="POST"
)
try:
    resp = urllib.request.urlopen(req, timeout=10)
    result = json.loads(resp.read())
    print("SUCCESS:", json.dumps(result)[:200])
except urllib.error.HTTPError as e:
    print("HTTP Error:", e.code, e.read().decode()[:200])
except Exception as e:
    print("Error:", e)
