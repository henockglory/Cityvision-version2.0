package ingest

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"

	"github.com/google/uuid"
)

func isDemoCameraMetadata(raw json.RawMessage) bool {
	if len(raw) == 0 {
		return false
	}
	var m map[string]interface{}
	if json.Unmarshal(raw, &m) != nil {
		return false
	}
	switch d := m["demo"].(type) {
	case bool:
		return d
	case string:
		return d == "true"
	}
	return false
}

// activeDemoCameraID returns the demo camera selected in org_demo_settings (video or camera mode).
func (o *Orchestrator) activeDemoCameraID(ctx context.Context, orgID uuid.UUID) (uuid.UUID, bool) {
	var sourceMode string
	var activeVideo, activeCam *uuid.UUID
	err := o.pool.QueryRow(ctx, `
		SELECT source_mode, active_video_id, active_camera_id
		FROM org_demo_settings WHERE org_id = $1`, orgID).Scan(&sourceMode, &activeVideo, &activeCam)
	if err != nil {
		return uuid.Nil, false
	}
	if sourceMode == "camera" && activeCam != nil && *activeCam != uuid.Nil {
		return *activeCam, true
	}
	if activeVideo != nil && *activeVideo != uuid.Nil {
		var camID uuid.UUID
		err := o.pool.QueryRow(ctx, `
			SELECT id FROM cameras
			WHERE org_id = $1 AND is_active = TRUE
			  AND metadata->>'demo_video_id' = $2
			LIMIT 1`, orgID, activeVideo.String()).Scan(&camID)
		if err == nil {
			return camID, true
		}
	}
	return uuid.Nil, false
}

// skipInactiveDemoCamera is true when a demo camera should not ingest (another demo video is selected).
func (o *Orchestrator) skipInactiveDemoCamera(ctx context.Context, orgID, cameraID uuid.UUID, meta json.RawMessage) bool {
	if !isDemoCameraMetadata(meta) {
		return false
	}
	active, ok := o.activeDemoCameraID(ctx, orgID)
	if !ok {
		return false
	}
	return cameraID != active
}

// skipNonDemoLiveCamera gates real (non-demo) camera ingest until LIVE_108_ENABLED is set.
func (o *Orchestrator) skipNonDemoLiveCamera(meta json.RawMessage) bool {
	if isDemoCameraMetadata(meta) {
		return false
	}
	var m map[string]interface{}
	if json.Unmarshal(meta, &m) != nil {
		return false
	}
	if m["virtual"] == true {
		return false
	}
	v := strings.TrimSpace(os.Getenv("LIVE_108_ENABLED"))
	return v != "1" && !strings.EqualFold(v, "true")
}

// frigateEvidenceIngestViaGo2RTC aligns IA timeline with Frigate by reading the same go2rtc loop.
func frigateEvidenceIngestViaGo2RTC() bool {
	switch strings.ToLower(strings.TrimSpace(os.Getenv("EVIDENCE_BACKEND"))) {
	case "frigate", "hybrid", "strict_frigate":
		return true
	}
	if strings.TrimSpace(os.Getenv("DEMO_MODE")) == "1" {
		switch strings.ToLower(strings.TrimSpace(os.Getenv("DEMO_EVIDENCE_BACKEND"))) {
		case "frigate", "hybrid", "strict_frigate":
			return true
		}
	}
	v := strings.TrimSpace(os.Getenv("FRIGATE_EVIDENCE"))
	return strings.EqualFold(v, "true") || v == "1"
}

func demoGo2rtcStreamFromMetadata(raw json.RawMessage) string {
	if len(raw) == 0 {
		return ""
	}
	var m map[string]interface{}
	if json.Unmarshal(raw, &m) != nil {
		return ""
	}
	if src, _ := m["go2rtc_src"].(string); strings.TrimSpace(src) != "" {
		return strings.TrimSpace(src)
	}
	return ""
}

// demoGo2rtcRTSPURL returns the looped demo stream URL served by citevision-v2-go2rtc.
func demoGo2rtcRTSPURL(raw json.RawMessage) string {
	src := demoGo2rtcStreamFromMetadata(raw)
	if src == "" {
		return ""
	}
	host := strings.TrimSpace(os.Getenv("GO2RTC_RTSP_HOST"))
	if host == "" {
		host = "127.0.0.1"
	}
	port := 8554
	if p := strings.TrimSpace(os.Getenv("GO2RTC_RTSP_PORT")); p != "" {
		if n, err := strconv.Atoi(p); err == nil && n > 0 {
			port = n
		}
	}
	return fmt.Sprintf("rtsp://%s:%d/%s", host, port, src)
}
