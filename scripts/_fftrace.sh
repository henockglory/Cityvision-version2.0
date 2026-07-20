#!/bin/bash
timeout 5 ffmpeg -loglevel trace -f lavfi -i testsrc=size=320x240:rate=15 -c:v libx264 -preset ultrafast -tune zerolatency -profile:v baseline -pix_fmt yuv420p -g 15 -t 2 -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/trace-pub 2>/tmp/fftrace.txt || true
grep -i rtsp /tmp/fftrace.txt | tail -30
echo '---ERR---'
grep -i error /tmp/fftrace.txt | tail -20
