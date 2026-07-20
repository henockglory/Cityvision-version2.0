#!/bin/bash
curl -s -X PUT 'http://127.0.0.1:1984/api/streams?name=test-manual-pub&src=publish'
echo
curl -s http://127.0.0.1:1984/api/streams | python3 -c 'import sys,json; d=json.load(sys.stdin); print("test-manual-pub" in d, d.get("test-manual-pub"))'
timeout 8 ffmpeg -loglevel warning -f lavfi -i testsrc=size=1280x720:rate=15 -c:v libx264 -preset ultrafast -tune zerolatency -profile:v baseline -pix_fmt yuv420p -g 15 -t 5 -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/test-manual-pub 2>&1 | tail -10
curl -s http://127.0.0.1:1984/api/streams | python3 -c 'import sys,json; d=json.load(sys.stdin); print("after pub", "test-manual-pub" in d, d.get("test-manual-pub"))'
