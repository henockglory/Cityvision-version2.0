import json, glob, sys
base = "/mnt/c/Users/gheno/citevision/shared/rule-catalog/*.json"
bad = []
for p in glob.glob(base):
    try:
        json.load(open(p, encoding="utf-8"))
    except Exception as e:
        bad.append((p, str(e)))
print("catalog files OK" if not bad else "ERRORS:")
for p, e in bad:
    print(" ", p, e)
sys.exit(1 if bad else 0)
