#!/usr/bin/env bash
set -euo pipefail
CAM=cv_d2eb7076-c3b3-40fd-9b2c-0d119bb975c9
BASE=http://127.0.0.1:5000
NOW=$(python3 -c 'import time; print(time.time())')
START=$(python3 -c "import time; print(time.time()-4)")
END=$(python3 -c "import time; print(time.time()+2)")
echo "wall now=$NOW start=$START end=$END"
for url in \
  "$BASE/api/$CAM/recordings/$START/$END/clip.mp4" \
  "$BASE/api/$CAM/start/$START/end/$END/clip.mp4"; do
  code=$(curl -s -o /tmp/tclip.mp4 -w '%{http_code}' "$url")
  sz=$(stat -c%s /tmp/tclip.mp4 2>/dev/null || echo 0)
  echo "url=$url -> http=$code size=$sz"
done
echo "--- events with has_clip ---"
curl -s "$BASE/api/events?cameras=$CAM&limit=3" | python3 -c "
import json,sys,time
ev=json.load(sys.stdin)
now=time.time()
for e in ev:
    st=e.get('start_time')
    print('id',e.get('id'),'start',st,'delta',round(abs(st-now),1) if st else None,'has_clip',e.get('has_clip'))
    if e.get('has_clip') and st:
        s=max(0,st-3); en=st+3
        print('  clip_url', f'$BASE/api/$CAM/recordings/{s}/{en}/clip.mp4')
"
