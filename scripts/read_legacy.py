#!/usr/bin/env python3
import json, glob
targets = ['tpl-intrusion', 'tpl-industrial-intrusion', 'tpl-line-cross', 'tpl-pedestrian-zone']
for fname in glob.glob('shared/rule-catalog/*.json'):
    data = json.load(open(fname))
    for t in (data if isinstance(data, list) else []):
        if not isinstance(t, dict): continue
        if t.get('id') in targets:
            print(f"=== {t['id']} ({fname}) ===")
            print(json.dumps(t.get('definition', {}), indent=2))
            print()
