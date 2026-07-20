import urllib.request, json, sys, os

# Source credentials from env or validation script defaults
sys.path.insert(0, os.path.expanduser('~/citevision-v2/scripts'))

API = 'http://127.0.0.1:8081'
EMAIL = os.environ.get('ADMIN_EMAIL', 'glory.henock@hologram.cd')
PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Hologram2026!')

def api(method, path, token=None, body=None):
    url = API + path
    data = json.dumps(body).encode() if body else None
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=15)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read()[:200]}", file=sys.stderr)
        return None

# Login
login = api('POST', '/api/v1/auth/login', body={'email': EMAIL, 'password': PASSWORD})
if not login:
    sys.exit(1)
token = login['access_token']
me = api('GET', '/api/v1/auth/me', token=token)
org = me.get('org_id', '')
print(f"Logged in as {EMAIL}, org={org}")

# Get rules
rules = api('GET', f'/api/v1/orgs/{org}/rules', token=token)
if not isinstance(rules, list):
    print("No rules found:", rules)
    sys.exit(1)

print(f"\nTotal rules: {len(rules)}")
for r in rules:
    name = r.get('name', '')
    if 'vitesse' in name.lower() or 'Ex' in name or 'speed' in name.lower():
        print(f"\nRule: {name}")
        print(f"  id: {r.get('id')}")
        print(f"  dedup_key_fields: {r.get('dedup_key_fields')}")
        print(f"  is_enabled: {r.get('is_enabled')}")
        conds = r.get('conditions') or []
        print(f"  conditions ({len(conds)}):")
        for c in conds:
            print(f"    {c}")
