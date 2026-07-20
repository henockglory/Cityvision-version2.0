#!/bin/bash
echo "=== tcp ==="
timeout 5 ffmpeg -loglevel warning -f lavfi -i testsrc=size=640x480:rate=15 -c:v libx264 -preset ultrafast -tune zerolatency -profile:v baseline -pix_fmt yuv420p -g 15 -t 3 -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/test-tr-tcp 2>&1 | tail -3
echo "=== udp ==="
timeout 5 ffmpeg -loglevel warning -f lavfi -i testsrc=size=640x480:rate=15 -c:v libx264 -preset ultrafast -tune zerolatency -profile:v baseline -pix_fmt yuv420p -g 15 -t 3 -f rtsp -rtsp_transport udp rtsp://127.0.0.1:8554/test-tr-udp 2>&1 | tail -3
