#!/usr/bin/env python3
"""Fix ffprobe.go with correct Go syntax"""
from pathlib import Path

ffprobe_go = r'''package camera

import (
	"context"
	"encoding/json"
	"os/exec"
	"strconv"
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

type ffprobeOutput struct {
	Streams []ffprobeStream `json:"streams"`
}

type ffprobeStream struct {
	CodecType   string `json:"codec_type"`
	CodecName   string `json:"codec_name"`
	Width       int    `json:"width"`
	Height      int    `json:"height"`
	RFrameRate  string `json:"r_frame_rate"`
}

// ProbeStreamFfprobe runs ffprobe on an RTSP URL and returns codec/resolution info.
// Returns Available=false if ffprobe is not installed.
// Timeout controls how long ffprobe is allowed to run (typical: 5–8 seconds).
func ProbeStreamFfprobe(ctx context.Context, rtspURL string, timeout time.Duration) FfprobeResult {
	if _, err := exec.LookPath("ffprobe"); err != nil {
		return FfprobeResult{Available: false}
	}
	if timeout == 0 {
		timeout = 7 * time.Second
	}

	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	cmd := exec.CommandContext(ctx,
		"ffprobe",
		"-v", "quiet",
		"-rtsp_transport", "tcp",
		"-timeout", "5000000",
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

	var probe ffprobeOutput
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
				res.FPS = parseRational(s.RFrameRate)
			}
		case "audio":
			if res.AudioCodec == "" {
				res.AudioCodec = s.CodecName
			}
		}
	}
	return res
}

// parseRational parses a fraction string like "25/1" or "30000/1001" to a float64.
func parseRational(s string) float64 {
	parts := strings.SplitN(s, "/", 2)
	if len(parts) != 2 {
		return 0
	}
	num, err1 := strconv.ParseFloat(strings.TrimSpace(parts[0]), 64)
	den, err2 := strconv.ParseFloat(strings.TrimSpace(parts[1]), 64)
	if err1 != nil || err2 != nil || den == 0 {
		return 0
	}
	fps := num / den
	// Round to 2 decimal places
	return float64(int(fps*100+0.5)) / 100
}
'''

target = Path("backend/internal/camera/ffprobe.go")
target.write_text(ffprobe_go, encoding="utf-8")
print(f"Rewrote {target} with correct Go syntax")
