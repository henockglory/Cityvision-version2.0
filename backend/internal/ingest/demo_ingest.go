package ingest

import (
	"context"
	"encoding/json"

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
