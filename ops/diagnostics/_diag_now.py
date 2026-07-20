#!/usr/bin/env python3
import subprocess, json, urllib.request, time

def psql(sql):
    r = subprocess.run(["docker", "exec", "citevision-v2-postgres",
                        "psql", "-U", "citevision", "-d", "citevision", "-t", "-A", "-c", sql],
                       capture_output=True, text=True)
    return r.stdout.strip()

print("=== ÉTAT ACTUEL ===\n")

# 1. Services
for name, url in [("Backend", "http://localhost:8081/health"),
                   ("AI", "http://localhost:8001/health"),
                   ("Rules", "http://localhost:8010/health")]:
    try:
        d = json.loads(urllib.request.urlopen(url, timeout=3).read())
        print(f"  {name}: {d.get('status','?')}")
    except:
        print(f"  {name}: DOWN")

# 2. AI PID et version capture.py
r = subprocess.run(["bash", "-c", "ps aux | grep uvicorn | grep -v grep | awk '{print $1,$2,\"started:\", $9}'"],
                   capture_output=True, text=True)
print(f"\n  AI PID: {r.stdout.strip()}")

r2 = subprocess.run(["bash", "-c", "stat -c '%y' ~/citevision-v2/ai-engine/src/citevision_ai/evidence/capture.py"],
                    capture_output=True, text=True)
print(f"  capture.py modifié: {r2.stdout.strip()[:40]}")

# 3. Speeding events dernières 5 min
recent = psql("SELECT count(*) FROM events WHERE event_type='speeding' AND occurred_at > NOW()-'5 minutes'::interval;")
recent_ev = psql("SELECT count(*) FROM events WHERE event_type='speeding' AND occurred_at > NOW()-'5 minutes'::interval AND jsonb_array_length(COALESCE(evidence_snapshot->'package'->'images','[]'::jsonb))>=2;")
alerts = psql("SELECT count(*) FROM alerts WHERE created_at > NOW()-'5 minutes'::interval;")
print(f"\n  Events speeding (5min): {recent} | avec evidence: {recent_ev} | alertes: {alerts}")

# 4. Dernier event speeding
last = psql("""
  SELECT to_char(occurred_at AT TIME ZONE 'Europe/Paris','HH24:MI:SS'),
         jsonb_array_length(COALESCE(evidence_snapshot->'package'->'images','[]'::jsonb)),
         evidence_snapshot->'package'->'images'->0->>'role',
         evidence_snapshot->'package'->'images'->1->>'role',
         evidence_snapshot->'package'->'images'->2->>'role'
  FROM events WHERE event_type='speeding' ORDER BY occurred_at DESC LIMIT 3;
""")
print(f"\n  Derniers events:")
for line in last.split('\n'):
    if line:
        p = line.split('|')
        print(f"    {p[0]} imgs={p[1]} roles={p[2]}/{p[3]}/{p[4]}")

# 5. Rules-engine activité récente
r3 = subprocess.run(["bash", "-c", "grep 'matched\\|synced' ~/citevision-v2/logs/rules-engine.log | tail -4"],
                    capture_output=True, text=True)
print(f"\n  Rules-engine log (dernier):\n{r3.stdout.strip()}")

# 6. AI zone_speed frames actifs ?
r4 = subprocess.run(["bash", "-c", "grep 'zone_speed\\|speeding\\|emitted' ~/citevision-v2/logs/ai-engine.log | grep -v '__pycache__' | tail -4"],
                    capture_output=True, text=True)
print(f"\n  AI logs récents:\n{r4.stdout.strip()}")

# 7. Vérifier que capture.py dans l'AI en cours a bien le fix subject
r5 = subprocess.run(["bash", "-c", "grep -n 'draw_bbox_on_frame\\|encode_scene.*subject\\|Full scene' ~/citevision-v2/ai-engine/src/citevision_ai/evidence/capture.py"],
                    capture_output=True, text=True)
print(f"\n  capture.py subject code:\n{r5.stdout.strip()}")
