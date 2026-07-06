package camera

import "strings"

// Go2RTCSourceForRTSP returns the go2rtc source URL (direct RTSP or ffmpeg transcode for WebRTC).
func Go2RTCSourceForRTSP(rtspURL string, stats *StreamStats) string {
	if stats == nil {
		return rtspURL
	}
	codec := strings.ToLower(stats.Codec)
	needsTranscode := stats.HasBFrames || codec == "hevc" || codec == "h265"
	if !needsTranscode {
		return rtspURL
	}
	return "ffmpeg:" + rtspURL + "#video=h264"
}
