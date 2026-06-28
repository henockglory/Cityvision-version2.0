package demo

import (
	"context"
	"encoding/json"
	"os"
	"strings"
	"time"

	"github.com/google/uuid"
)

// StartRetentionJanitor purges demo events/alerts/evidence on a fixed interval.
func (s *Service) StartRetentionJanitor(ctx context.Context) {
	ticker := time.NewTicker(60 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			s.runRetentionPass(ctx)
		}
	}
}

func (s *Service) runRetentionPass(ctx context.Context) {
	cutoff := time.Now().Add(-RetentionMinutes * time.Minute)
	orgs, err := s.listOrgsWithDemoData(ctx)
	if err != nil {
		s.log.Warn("demo retention org list failed", "error", err)
		return
	}
	for _, orgID := range orgs {
		if err := s.purgeExpiredDemo(ctx, orgID, cutoff); err != nil {
			s.log.Warn("demo retention purge failed", "org_id", orgID, "error", err)
		}
		if err := s.trimDemoEventsTotal(ctx, orgID); err != nil {
			s.log.Warn("demo retention trim failed", "org_id", orgID, "error", err)
		}
	}
}

func (s *Service) listOrgsWithDemoData(ctx context.Context) ([]uuid.UUID, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT DISTINCT org_id FROM events WHERE payload->>'demo' = 'true'
		UNION
		SELECT DISTINCT org_id FROM alerts WHERE metadata->>'demo' = 'true'`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var ids []uuid.UUID
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err != nil {
			continue
		}
		ids = append(ids, id)
	}
	return ids, rows.Err()
}

func (s *Service) purgeExpiredDemo(ctx context.Context, orgID uuid.UUID, cutoff time.Time) error {
	_, err := s.pool.Exec(ctx, `
		DELETE FROM events
		WHERE org_id = $1 AND payload->>'demo' = 'true' AND ingested_at < $2`, orgID, cutoff)
	if err != nil {
		return err
	}
	_, err = s.pool.Exec(ctx, `
		DELETE FROM alerts
		WHERE org_id = $1 AND metadata->>'demo' = 'true' AND created_at < $2`, orgID, cutoff)
	if err != nil {
		return err
	}
	if s.minio != nil && s.minio.Available() {
		prefix := "raw/" + orgID.String() + "/"
		_, _ = s.minio.RemovePrefix(ctx, prefix)
	}
	if s.evidence != nil {
		_, _ = s.evidence.PurgeDemoPrefix(ctx, orgID)
	}
	return nil
}

func (s *Service) trimDemoEventsTotal(ctx context.Context, orgID uuid.UUID) error {
	var cnt int
	err := s.pool.QueryRow(ctx, `
		SELECT COUNT(*) FROM events
		WHERE org_id = $1 AND payload->>'demo' = 'true'`, orgID).Scan(&cnt)
	if err != nil {
		return err
	}
	excess := cnt - MaxDemoEventsTotal
	if excess <= 0 {
		return nil
	}
	_, err = s.pool.Exec(ctx, `
		DELETE FROM events WHERE id IN (
			SELECT id FROM events
			WHERE org_id = $1 AND payload->>'demo' = 'true'
			ORDER BY ingested_at ASC
			LIMIT $2
		)`, orgID, excess)
	return err
}

// ResetWorkspace clears demo events, alerts, watchlists, evidence, and all uploaded videos.
// Rules are intentionally preserved — they are user configuration, not demo data.
func (s *Service) ResetWorkspace(ctx context.Context, orgID uuid.UUID) (map[string]interface{}, error) {
	out := map[string]interface{}{"status": "demo_reset"}

	tag, err := s.pool.Exec(ctx, `
		DELETE FROM events WHERE org_id = $1 AND payload->>'demo' = 'true'`, orgID)
	if err != nil {
		return nil, err
	}
	out["events_deleted"] = tag.RowsAffected()

	tag, err = s.pool.Exec(ctx, `
		DELETE FROM alerts WHERE org_id = $1 AND metadata->>'demo' = 'true'`, orgID)
	if err != nil {
		return nil, err
	}
	out["alerts_deleted"] = tag.RowsAffected()

	tag, err = s.pool.Exec(ctx, `DELETE FROM surveillance_lists WHERE org_id = $1`, orgID)
	if err == nil {
		out["watchlists_deleted"] = tag.RowsAffected()
	}

	// Delete all demo videos (including go2rtc streams and virtual cameras).
	videos, _ := s.listVideos(ctx, orgID)
	var videosDeleted int64
	for _, v := range videos {
		vrow, err := s.getVideo(ctx, orgID, v.ID)
		if err != nil {
			continue
		}
		if vrow.Go2rtcSrc != "" {
			_ = s.go2rtc.DeleteStream(ctx, vrow.Go2rtcSrc)
		}
		if vrow.LocalPath != "" {
			_ = os.Remove(vrow.LocalPath)
		}
		if vrow.minioRawKey != "" && !strings.HasPrefix(vrow.minioRawKey, "raw/") {
			_ = os.Remove(vrow.minioRawKey)
		}
		camID := s.findVirtualCameraByVideoID(ctx, orgID, v.ID)
		if camID != uuid.Nil {
			_ = s.cameras.Delete(ctx, orgID, camID)
		}
		videosDeleted++
	}
	tag, _ = s.pool.Exec(ctx, `DELETE FROM org_demo_videos WHERE org_id = $1`, orgID)
	if tag.RowsAffected() > videosDeleted {
		videosDeleted = tag.RowsAffected()
	}
	out["videos_deleted"] = videosDeleted

	// Clear active video/camera from settings.
	_, _ = s.pool.Exec(ctx, `
		UPDATE org_demo_settings SET active_video_id = NULL, active_camera_id = NULL, source_mode = 'video', updated_at = NOW()
		WHERE org_id = $1`, orgID)

	if s.minio != nil && s.minio.Available() {
		n, _ := s.minio.RemovePrefix(ctx, "raw/"+orgID.String()+"/")
		out["demo_video_objects_deleted"] = n
	}
	if s.evidence != nil {
		n, _ := s.evidence.PurgeDemoPrefix(ctx, orgID)
		out["evidence_objects_deleted"] = n
	}
	return out, nil
}

// TagEventPayload marks payload as demo when the source camera is a demo camera.
func (s *Service) TagEventPayload(ctx context.Context, cameraID *uuid.UUID, payload map[string]interface{}) {
	if cameraID == nil || payload == nil {
		return
	}
	var meta []byte
	err := s.pool.QueryRow(ctx, `SELECT metadata FROM cameras WHERE id = $1`, *cameraID).Scan(&meta)
	if err != nil {
		return
	}
	var camMeta map[string]interface{}
	if err := json.Unmarshal(meta, &camMeta); err != nil {
		return
	}
	isDemo := false
	if d, ok := camMeta["demo"].(bool); ok && d {
		isDemo = true
	}
	if ds, ok := camMeta["demo"].(string); ok && ds == "true" {
		isDemo = true
	}
	if !isDemo {
		return
	}
	payload["demo"] = true
	if vid, ok := camMeta["demo_video_id"].(string); ok && vid != "" {
		payload["demo_video_id"] = vid
	}
	payload["demo_camera_id"] = cameraID.String()
}
