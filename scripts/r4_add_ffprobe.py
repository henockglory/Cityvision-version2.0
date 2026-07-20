#!/usr/bin/env python3
"""
R4 – Add ffprobe-based stream validation to camera probe:
  1. Create backend/internal/camera/ffprobe.go with ProbeStreamFfprobe()
  2. Patch ProbeResult to include ffprobe fields
  3. Patch ProbeCredentials to run ffprobe on the best candidate
  4. Update frontend wizard UI to show ffprobe result
"""
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# 1. Create backend/internal/camera/ffprobe.go
# ──────────────────────────────────────────────────────────────────────────────
ffprobe_go = r'''package camera

import (
	"context"
	"encoding/json"
	"os/exec"
	"strings"
	"time"
)

// FfprobeResult holds the stream info returned by ffprobe.
type FfprobeResult struct {
	VideoCodec string  `json:"video_codec,omitempty"`
	Width      int     `json:"width,omitempty"`
	Height     int     `json:"height,omitempty"`
	FPS        float64 `json:"fps,omitempty"`
	AudioCodec string  `json:"audio_codec,omitempty"`
	ErrorMsg   string  `json:"error,omitempty"`
	Available  bool    `json:"available"` // false when ffprobe binary not found
}

type ffprobeStreams struct {
	Streams []struct {
		CodecType string `json:"codec_type"`
		CodecName string `json:"codec_name"`
		Width     int    `json:"width"`
		Height    int    `json:"height"`
		RFrameRate string `json:"r_frame_rate"`
	} `json:"streams"`
}

// ProbeStreamFfprobe runs ffprobe on an RTSP URL and returns codec/resolution info.
// Returns a zero FfprobeResult with Available=false if ffprobe is not installed.
// Timeout controls how long ffprobe is allowed to run (typ. 5–8 seconds).
func ProbeStreamFfprobe(ctx context.Context, rtspURL string, timeout time.Duration) FfprobeResult {
	if _, err := exec.LookPath("ffprobe"); err != nil {
		return FfprobeResult{Available: false}
	}
	if timeout == 0 {
		timeout = 7 * time.Second
	}

	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	// -timeout / -rtsp_transport tcp ensure we don't hang on unreachable streams
	cmd := exec.CommandContext(ctx,
		"ffprobe",
		"-v", "quiet",
		"-rtsp_transport", "tcp",
		"-timeout", "5000000", // microseconds
		"-print_format", "json",
		"-show_streams",
		rtspURL,
	)
	out, err := cmd.Output()
	if err != nil {
		msg := err.Error()
		if ctx.Err() != nil {
			msg = "timeout après " + timeout.String()
		}
		return FfprobeResult{Available: true, ErrorMsg: msg}
	}

	var probe ffprobeStreams
	if jsonErr := json.Unmarshal(out, &probe); jsonErr != nil {
		return FfprobeResult{Available: true, ErrorMsg: "impossible de parser la réponse ffprobe"}
	}

	res := FfprobeResult{Available: true}
	for _, s := range probe.Streams {
		switch s.CodecType {
		case "video":
			if res.VideoCodec == "" {
				res.VideoCodec = s.CodecName
				res.Width = s.Width
				res.Height = s.Height
				// Parse r_frame_rate like "25/1" or "30000/1001"
				parts := strings.SplitN(s.RFrameRate, "/", 2)
				if len(parts) == 2 {
					var num, den float64
					if _, e1 := (&num); true {
						_ = e1
					}
					// simple parse
					fmt_sscanf(&num, parts[0])
					fmt_sscanf(&den, parts[1])
					if den > 0 {
						res.FPS = roundFPS(num / den)
					}
				}
			}
		case "audio":
			if res.AudioCodec == "" {
				res.AudioCodec = s.CodecName
			}
		}
	}
	return res
}

func fmt_sscanf(dst *float64, s string) {
	for _, c := range s {
		if c >= '0' && c <= '9' {
			*dst = *dst*10 + float64(c-'0')
		}
	}
}

func roundFPS(f float64) float64 {
	// Round to 2 decimal places
	return float64(int(f*100+0.5)) / 100
}
'''

ffprobe_path = Path("backend/internal/camera/ffprobe.go")
ffprobe_path.write_text(ffprobe_go, encoding="utf-8")
print(f"Created {ffprobe_path}")

# ──────────────────────────────────────────────────────────────────────────────
# 2. Patch ProbeResult and ProbeCandidate in wizard.go to include ffprobe
# ──────────────────────────────────────────────────────────────────────────────
wizard_file = Path("backend/internal/camera/wizard.go")
wizard_content = wizard_file.read_text(encoding="utf-8")

OLD_PROBE_RESULT = '''type ProbeResult struct {
	Host       string           `json:"host"`
	Best       *ProbeCandidate  `json:"best,omitempty"`
	Candidates []ProbeCandidate `json:"candidates"`
}'''

NEW_PROBE_RESULT = '''type ProbeResult struct {
	Host       string           `json:"host"`
	Best       *ProbeCandidate  `json:"best,omitempty"`
	Candidates []ProbeCandidate `json:"candidates"`
	Ffprobe    *FfprobeResult   `json:"ffprobe,omitempty"` // nil when best is nil or ffprobe not installed
}'''

if 'Ffprobe' in wizard_content:
    print("wizard.go already patched")
elif OLD_PROBE_RESULT in wizard_content:
    wizard_content = wizard_content.replace(OLD_PROBE_RESULT, NEW_PROBE_RESULT)
    # Patch ProbeCredentials to call ffprobe on the best candidate
    OLD_RESULT_BEST = '''	result.Best = best
	return result
}'''
    NEW_RESULT_BEST = '''	result.Best = best
	// Run ffprobe on best candidate for deeper validation (async-safe, 7s timeout)
	if best != nil {
		// Reconstruct the actual URL (without masking) from request params
		ffURL := BuildRTSPURL(best.Vendor, req.Host, req.Port, req.Channel, req.Username, req.Password, best.RTSPPath, best.Profile)
		ffResult := ProbeStreamFfprobe(ctx, ffURL, 7*time.Second)
		result.Ffprobe = &ffResult
	}
	return result
}'''
    wizard_content = wizard_content.replace(OLD_RESULT_BEST, NEW_RESULT_BEST)
    wizard_file.write_text(wizard_content, encoding="utf-8")
    print("Patched wizard.go with ffprobe integration")
else:
    print("ERROR: ProbeResult anchor not found in wizard.go")

# ──────────────────────────────────────────────────────────────────────────────
# 3. Patch frontend Cameras.tsx wizard to display ffprobe results
# ──────────────────────────────────────────────────────────────────────────────
cameras_file = Path("frontend/src/pages/Cameras.tsx")
cameras_content = cameras_file.read_text(encoding="utf-8")

# Find where probe result is displayed (step 3 "testOk" section)
# Add ffprobe info badge next to "connexion réussie"
OLD_TEST_OK = '''testOk && ('''
if OLD_TEST_OK not in cameras_content:
    # Try to find the probe result display block
    print("WARN: Could not find testOk anchor in Cameras.tsx — skipping UI patch (manual step required)")
else:
    # Look for the success message display
    OLD_SUCCESS = "t('cameras.step3.testOkMsg')"
    if OLD_SUCCESS in cameras_content:
        # Find context around it
        idx = cameras_content.find(OLD_SUCCESS)
        snippet = cameras_content[max(0,idx-200):idx+300]
        print("Found testOkMsg context - adding ffprobe details nearby")
        # We'll add the ffprobe info after the success message
        OLD_SUCCESS_BLOCK = "t('cameras.step3.testOkMsg')"
        # Check if ffprobe field is already shown
        if 'ffprobe' not in cameras_content.lower():
            NEW_SUCCESS_BLOCK = '''t('cameras.step3.testOkMsg')}
                {probeResult?.ffprobe?.video_codec && (
                  <span className="text-xs text-cv-muted/80 mt-0.5 block">
                    {probeResult.ffprobe.video_codec.toUpperCase()}
                    {probeResult.ffprobe.width ? ` · ${probeResult.ffprobe.width}×${probeResult.ffprobe.height}` : ''}
                    {probeResult.ffprobe.fps ? ` · ${probeResult.ffprobe.fps} fps` : ''}
                  </span>
                )}
                {probeResult?.ffprobe?.error && (
                  <span className="text-xs text-amber-400 mt-0.5 block">
                    {t('cameras.step3.ffprobeWarn', { msg: probeResult.ffprobe.error })}
                  </span>
                '''
            cameras_content = cameras_content.replace(OLD_SUCCESS_BLOCK, NEW_SUCCESS_BLOCK, 1)
            cameras_file.write_text(cameras_content, encoding="utf-8")
            print("Patched Cameras.tsx with ffprobe info display")
        else:
            print("Cameras.tsx already has ffprobe display")
    else:
        print("WARN: testOkMsg key not found in Cameras.tsx")

# ──────────────────────────────────────────────────────────────────────────────
# 4. Add ffprobe translation keys to fr.json
# ──────────────────────────────────────────────────────────────────────────────
import json
fr_file = Path("frontend/src/i18n/fr.json")
data = json.loads(fr_file.read_text(encoding="utf-8"))

cameras = data.setdefault("cameras", {})
cameras.update({
    "step3.ffprobeWarn": "Aperçu ffprobe partiel : {{msg}}",
    "step3.ffprobeSuccess": "Flux validé par ffprobe",
})

fr_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
json.loads(fr_file.read_text(encoding="utf-8"))  # validate
print("Added ffprobe i18n keys + JSON valid ✓")
