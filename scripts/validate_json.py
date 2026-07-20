import json, sys
path = sys.argv[1]
try:
    json.load(open(path, encoding='utf-8'))
    print('JSON OK')
except json.JSONDecodeError as e:
    print(f'JSON ERROR: {e}')
    sys.exit(1)
