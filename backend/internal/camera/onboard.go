package camera

import (
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"strconv"
	"strings"
	"time"

	"github.com/citevision/citevision-v2/backend/internal/models"
)

// StreamStats holds ffprobe results for onboarding.
type StreamStats struct {
	Codec      string  `json:"codec"`
	FPS        float64 `json:"fps"`
	Width      int     `json:"width"`
	Height     int     `json:"height"`
	HasBFrames bool    `json:"has_b_frames"`
}

// ProbeStreamStats runs ffprobe (3s timeout) on an RTSP URL.
func ProbeStreamStats(ctx context.Context, rtspURL string) (*StreamStats, error) {
	if rtspURL == "" {
		return nil, fmt.Errorf("empty rtsp url")
	}
	ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "ffprobe",
		"-v", "error",
		"-select_streams", "v:0",
		"-show_entries", "stream=codec_name,r_frame_rate,width,height,has_b_frames",
		"-of", "json",
		rtspURL,
	)
	out, err := cmd.Output()
	if err != nil {
		return nil, err
	}
	var parsed struct {
		Streams []struct {
			CodecName  string `json:"codec_name"`
			RFrameRate string `json:"r_frame_rate"`
			Width      int    `json:"width"`
			Height     int    `json:"height"`
			HasBFrames int    `json:"has_b_frames"`
		} `json:"streams"`
	}
	if err := json.Unmarshal(out, &parsed); err != nil {
		return nil, err
	}
	if len(parsed.Streams) == 0 {
		return nil, fmt.Errorf("no video stream")
	}
	s := parsed.Streams[0]
	fps := parseFrameRate(s.RFrameRate)
	return &StreamStats{
		Codec:      s.CodecName,
		FPS:        fps,
		Width:      s.Width,
		Height:     s.Height,
		HasBFrames: s.HasBFrames > 0,
	}, nil
}

func parseFrameRate(rate string) float64 {
	parts := strings.Split(rate, "/")
	if len(parts) != 2 {
		return 25
	}
	num, _ := strconv.ParseFloat(parts[0], 64)
	den, _ := strconv.ParseFloat(parts[1], 64)
	if den <= 0 {
		return 25
	}
	return num / den
}

// OnboardCamera registers go2rtc stream and enriches camera metadata.
func OnboardCamera(ctx context.Context, cam *models.Camera, rtspURL string) error {
	if cam == nil || rtspURL == "" {
		return nil
	}
	meta := map[string]interface{}{}
	if len(cam.Metadata) > 0 {
		_ = json.Unmarshal(cam.Metadata, &meta)
	}
	streamName := fmt.Sprintf("cam-%s", cam.ID.String())
	go2 := NewGo2RTCClient()
	regURL := rtspURL
	if stats, err := ProbeStreamStats(ctx, rtspURL); err == nil && stats != nil {
		meta["stream_stats"] = stats
		if stats.HasBFrames {
			// Relay through go2rtc transcode policy when B-frames break WebRTC
			meta["transcode"] = true
		}
	}
	if _, err := go2.RegisterStream(ctx, streamName, regURL); err == nil {
		meta["go2rtc_src"] = streamName
	}
	raw, _ := json.Marshal(meta)
	cam.Metadata = raw
	return nil
}
