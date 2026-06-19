import json, sys
path = sys.argv[1] if len(sys.argv) > 1 else '/home/gheno/citevision-v2/shared/rule-catalog/intrusion-loitering-line-theft.json'
data = json.load(open(path, encoding='utf-8'))
for t in data:
    if t['id'] in ('tpl-loitering', 'tpl-crowd-density'):
        print(t['id'])
        print(json.dumps(t['definition'], indent=2))
