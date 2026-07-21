package camera

import (
	"fmt"
	"net/url"
	"strings"
)

// Browser-unsafe codecs for WebRTC/MSE preview (Chrome/Edge cannot play HEVC reliably).
var unsafePreviewCodecs = map[string]struct{}{
	"hevc": {}, "h265": {}, "hev1": {}, "hvc1": {},
	"mpeg4": {}, "mpeg2video": {}, "vp9": {}, // vp9 ok in some browsers but go2rtc webrtc prefers h264
}

// Go2RTCSourceForRTSP returns the preferred go2rtc source for live preview.
// Live RTSP is always wrapped in ffmpeg→H264 so browsers never see HEVC/RPS dumps.
func Go2RTCSourceForRTSP(rtspURL string, stats *StreamStats) string {
	srcs := Go2RTCSourcesForRTSP(rtspURL, stats)
	if len(srcs) == 0 {
		return ffmpegH264Source(rtspURL)
	}
	return srcs[0]
}

// Go2RTCSourcesForRTSP returns ordered failover sources (browser-safe first).
func Go2RTCSourcesForRTSP(rtspURL string, stats *StreamStats) []string {
	rtspURL = strings.TrimSpace(rtspURL)
	if rtspURL == "" {
		return nil
	}
	out := make([]string, 0, 4)
	add := func(s string) {
		s = strings.TrimSpace(s)
		if s == "" {
			return
		}
		for _, e := range out {
			if e == s {
				return
			}
		}
		out = append(out, s)
	}

	// Always prefer forced H264 transcode for WebRTC (HEVC/B-frames/unknown codecs).
	forceTranscode := true
	if stats != nil {
		codec := strings.ToLower(strings.TrimSpace(stats.Codec))
		if codec == "h264" || codec == "avc1" || codec == "avc" {
			if !stats.HasBFrames {
				// Still transcode by default for stable WebRTC; allow copy only as last resort.
				forceTranscode = true
			}
		}
		if _, bad := unsafePreviewCodecs[codec]; bad || codec == "" {
			forceTranscode = true
		}
	}

	add(ffmpegH264Source(rtspURL))
	add(ffmpegH264HardwareSource(rtspURL))

	// Alternate H264-friendly RTSP paths (Hikvision/Dahua substreams often already H264).
	for _, alt := range alternateRTSPPaths(rtspURL) {
		add(ffmpegH264Source(alt))
	}

	if !forceTranscode {
		add(rtspURL) // raw only as last resort when probe says clean H264
	}
	return out
}

func ffmpegH264Source(rtspURL string) string {
	// video=h264 forces libx264 in go2rtc ffmpeg module.
	// Do NOT use #audio=none — go2rtc 1.9 treats "none" as an output filename and fails with
	// "Unable to choose an output format for 'none'". Omit audio (video-only) instead.
	return "ffmpeg:" + encodeRTSPForGo2RTC(rtspURL) + "#video=h264"
}

func ffmpegH264HardwareSource(rtspURL string) string {
	return "ffmpeg:" + encodeRTSPForGo2RTC(rtspURL) + "#video=h264#hardware"
}

// encodeRTSPForGo2RTC percent-encodes userinfo special chars (+ becomes space if left raw).
func encodeRTSPForGo2RTC(rtspURL string) string {
	u, err := url.Parse(rtspURL)
	if err != nil || u.User == nil {
		return rtspURL
	}
	user := u.User.Username()
	pass, hasPass := u.User.Password()
	if !hasPass {
		return rtspURL
	}
	u.User = url.UserPassword(user, pass) // UserPassword encodes reserved chars in password
	return u.String()
}

// alternateRTSPPaths derives common H264 substream URLs from a main RTSP URL.
func alternateRTSPPaths(rtspURL string) []string {
	u, err := url.Parse(rtspURL)
	if err != nil || u.Scheme == "" {
		return nil
	}
	path := u.Path
	var alts []string
	switch {
	case strings.Contains(path, "/Streaming/Channels/101"):
		u2 := *u
		u2.Path = strings.Replace(path, "/Streaming/Channels/101", "/Streaming/Channels/102", 1)
		alts = append(alts, u2.String())
	case strings.Contains(path, "/Streaming/Channels/1"):
		u2 := *u
		u2.Path = strings.Replace(path, "/Streaming/Channels/1", "/Streaming/Channels/102", 1)
		alts = append(alts, u2.String())
	case strings.HasSuffix(path, "/live") || path == "/live":
		u2 := *u
		u2.Path = "/Streaming/Channels/102"
		alts = append(alts, u2.String())
		u3 := *u
		u3.Path = "/h264Preview_01_sub"
		alts = append(alts, u3.String())
	case strings.Contains(path, "/cam/realmonitor"):
		// Dahua: subtype=1 is usually substream
		q := u.Query()
		if q.Get("subtype") == "0" || q.Get("subtype") == "" {
			u2 := *u
			qq := u2.Query()
			qq.Set("subtype", "1")
			u2.RawQuery = qq.Encode()
			alts = append(alts, u2.String())
		}
	}
	return alts
}

// NeedsPreviewTranscode reports whether WebRTC would be unsafe without ffmpeg H264.
func NeedsPreviewTranscode(stats *StreamStats) bool {
	if stats == nil {
		return true
	}
	codec := strings.ToLower(strings.TrimSpace(stats.Codec))
	if codec == "" {
		return true
	}
	if _, bad := unsafePreviewCodecs[codec]; bad {
		return true
	}
	if stats.HasBFrames {
		return true
	}
	return false
}

// IsCodecErrorMessage detects ffmpeg/HEVC/WebRTC dumps that must never surface raw in UI.
func IsCodecErrorMessage(msg string) bool {
	l := strings.ToLower(msg)
	needles := []string{
		"hevc", "h265", "poc", "frame rps", "error constructing",
		"webrtc/offer", "exec/rtsp", "could not find ref",
		"not enough frames to estimate rate", "invalid data found",
	}
	for _, n := range needles {
		if strings.Contains(l, n) {
			return true
		}
	}
	return false
}

// StreamNameForCamera builds the canonical go2rtc stream id.
func StreamNameForCamera(cameraID string) string {
	return fmt.Sprintf("cam-%s", cameraID)
}
