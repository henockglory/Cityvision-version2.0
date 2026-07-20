import subprocess, numpy as np, time
cmd = ["ffmpeg","-loglevel","warning","-y","-f","rawvideo","-pix_fmt","bgr24","-s","1280x720","-r","15","-i","pipe:0","-c:v","libx264","-preset","ultrafast","-tune","zerolatency","-profile:v","baseline","-pix_fmt","yuv420p","-g","15","-bf","0","-f","rtsp","-rtsp_transport","tcp","rtsp://127.0.0.1:8554/test-pipe-pub"]
p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
frame = np.zeros((720,1280,3), dtype=np.uint8)
frame[:,:,1] = 128
err = None
for i in range(30):
    try:
        p.stdin.write(frame.tobytes())
        p.stdin.flush()
    except Exception as e:
        err = e; break
    time.sleep(1/15)
try:
    p.stdin.close()
except: pass
rc = p.wait(timeout=5)
stderr = p.stderr.read().decode(errors='replace') if p.stderr else ''
print('rc', rc, 'err', err)
print('stderr', stderr[-800:])
