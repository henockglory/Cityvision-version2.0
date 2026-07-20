#!/usr/bin/env python3
import os
import subprocess
import sys

os.chdir("/home/gheno/citevision-v2")
os.environ["ADMIN_PASSWORD"] = "Henockglory@03"
os.environ["TARGET_DETECTIONS"] = "1"
os.environ["RULE_TIMEOUT_SEC"] = "420"
os.environ["RULE_SYNC_WAIT_SEC"] = "45"
os.environ["REPORT_TAG"] = "frigate-retest"
os.environ["VALIDATE_ONLY"] = "Démo · Excès de vitesse,Démo · Téléphone au volant,Démo · Feu rouge"

log = "/home/gheno/citevision-v2/logs/validate-3rules-run.log"
with open(log, "w", encoding="utf-8") as f:
    f.write("=== validation 3 rules started ===\n")
    sys.stdout.flush()
    rc = subprocess.call([sys.executable, "scripts/validate_demo_five_rules.py"], stdout=f, stderr=subprocess.STDOUT)
    f.write(f"\n=== exit {rc} ===\n")
sys.exit(rc)
