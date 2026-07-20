#!/usr/bin/env python3
"""Analyze catalog: find legacy definitions, missing event_type, untagged partiels."""
import json, glob
from pathlib import Path

all_templates = {}
for f in sorted(glob.glob('shared/rule-catalog/*.json')):
    fname = Path(f).name
    data = json.load(open(f))
    items = data if isinstance(data, list) else data.get('templates', [])
    for t in items:
        if not isinstance(t, dict): continue
        tid = t.get('id','')
        if tid and tid not in all_templates:
            all_templates[tid] = {**t, '_file': fname}

def has_op(node, op_name):
    if not isinstance(node, dict): return False
    if node.get('op','').lower() == op_name.lower(): return True
    return any(has_op(c, op_name) for c in node.get('children',[]))

def has_field(node, field_name):
    if not isinstance(node, dict): return False
    if node.get('field','').lower() == field_name.lower(): return True
    return any(has_field(c, field_name) for c in node.get('children',[]))

print("=== LEGACY OPS (need event_type migration) ===")
for tid, t in sorted(all_templates.items()):
    cond = t.get('definition', {}).get('condition', {})
    has_iz = has_op(cond, 'in_zone')
    has_cl = has_op(cond, 'cross_line')
    has_et = has_field(cond, 'event_type')
    if (has_iz or has_cl) and not has_et:
        print(f"  {tid}: in_zone={has_iz} cross_line={has_cl} [{t['_file']}]")

print("")
print("=== NO PARTIAL_STATUS (need tagging) ===")
for tid, t in sorted(all_templates.items()):
    ps = t.get('partial_status', '')
    if not ps:
        cond = t.get('definition', {}).get('condition', {})
        has_et = has_field(cond, 'event_type')
        print(f"  {tid}: event_type_in_def={has_et} [{t['_file']}]")

print("")
print(f"TOTAL: {len(all_templates)} unique templates")
