# Vendor Dependencies

Clone these open-source projects into `vendor/` (not committed). Citévision v2 integrates with them via adapters; upstream code stays vendored separately.

| Project | Repository | Purpose |
|---------|------------|---------|
| **ByteTrack** | https://github.com/ifzhang/ByteTrack | Multi-object tracking reference implementation |
| **go2rtc** | https://github.com/AlexxIT/go2rtc | RTSP/WebRTC stream relay and transcoding |
| **ONVIF** | https://github.com/use-go/onvif | ONVIF camera discovery and PTZ control |

## Clone commands

```bash
mkdir -p vendor
git clone --depth 1 https://github.com/ifzhang/ByteTrack.git vendor/ByteTrack
git clone --depth 1 https://github.com/AlexxIT/go2rtc.git vendor/go2rtc
git clone --depth 1 https://github.com/use-go/onvif.git vendor/onvif
```

## Notes

- **ByteTrack**: The AI engine ships a lightweight ByteTrack-inspired tracker in Python; the upstream repo is for reference and future ONNX export alignment.
- **go2rtc**: Used by the video pipeline for RTSP ingest fallback and browser preview.
- **ONVIF**: Camera discovery in later phases; not required for Phase 1 validation.
