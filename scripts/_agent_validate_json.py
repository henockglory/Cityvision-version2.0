import json, sys
p = "/mnt/c/Users/gheno/citevision/shared/zone-behaviors.json"
d = json.load(open(p, encoding="utf-8"))
missing = [b.get("id") for b in d["behaviors"] if "applies_to" not in b]
print("OK behaviors:", len(d["behaviors"]))
print("missing applies_to:", missing)
sys.exit(1 if missing else 0)
