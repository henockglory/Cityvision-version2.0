package ingest

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"time"

	"github.com/google/uuid"

	"github.com/citevision/citevision-v2/backend/internal/demo"
)

const (
	demoHealIngestMinFrames = 30
	demoHealTimeout         = 90 * time.Second
)

// DemoSwitchHeal re-orchestrates ingest, streams, evidence offsets and rules after a demo
// video/camera change. Intended to run on every PATCH /demo/settings that switches source.
func (o *Orchestrator) DemoSwitchHeal(
	ctx context.Context,
	demoSvc *demo.Service,
	orgID uuid.UUID,
	prevCamID *uuid.UUID,
	newCamID *uuid.UUID,
	videoID *uuid.UUID,
) error {
	if o == nil {
		return nil
	}
	healCtx, cancel := context.WithTimeout(ctx, demoHealTimeout)
	defer cancel()

	log := o.log
	if log == nil {
		log = slog.Default()
	}

	if demoSvc != nil {
		if videoID != nil {
			demoSvc.EnsureVideoStream(healCtx, orgID, *videoID)
		} else {
			demoSvc.RepairAllDemoStreams(healCtx)
		}
	}

	if prevCamID != nil && newCamID != nil && *prevCamID != *newCamID {
		o.forceStopCamera(healCtx, *prevCamID)
	}

	if newCamID != nil {
		prev := ""
		if prevCamID != nil {
			prev = prevCamID.String()
		}
		if err := o.ai.ResetDemoActivate(healCtx, newCamID.String(), prev); err != nil {
			log.Warn("demo heal: ai reset failed", "camera_id", newCamID, "error", err)
		}
		o.forceRestartCamera(newCamID)
	}

	o.InvalidateConfigHashes()
	o.SyncNow(healCtx)
	o.triggerRulesSync(healCtx)

	if o.frigateHooks.Rebuild != nil {
		if err := o.frigateHooks.Rebuild(healCtx); err != nil {
			log.Warn("demo heal: frigate rebuild failed", "error", err)
		}
	}

	if newCamID == nil {
		return nil
	}
	if err := o.waitIngestReady(healCtx, newCamID.String(), demoHealIngestMinFrames); err != nil {
		return fmt.Errorf("demo ingest not ready: %w", err)
	}
	if o.frigateHooks.WaitFresh != nil {
		if err := o.frigateHooks.WaitFresh(healCtx, newCamID.String(), 25); err != nil {
			return fmt.Errorf("frigate not fresh: %w", err)
		}
	}
	log.Info("demo switch heal complete", "org_id", orgID, "camera_id", newCamID)
	return nil
}

func (o *Orchestrator) forceStopCamera(ctx context.Context, camID uuid.UUID) {
	o.mu.Lock()
	delete(o.active, camID)
	delete(o.configHash, camID)
	delete(o.failNext, camID)
	o.mu.Unlock()
	_ = o.ai.StopCamera(ctx, camID.String())
}

func (o *Orchestrator) forceRestartCamera(camID *uuid.UUID) {
	if camID == nil {
		return
	}
	o.mu.Lock()
	delete(o.active, *camID)
	delete(o.configHash, *camID)
	delete(o.failNext, *camID)
	o.mu.Unlock()
}

func (o *Orchestrator) triggerRulesSync(ctx context.Context) {
	base := os.Getenv("RULES_ENGINE_URL")
	if base == "" {
		base = "http://127.0.0.1:8010"
	}
	_ = o.ai.PostEmpty(ctx, base+"/internal/sync-rules")
}

// TriggerRulesSyncNow asks rules-engine to reload active rules immediately.
func (o *Orchestrator) TriggerRulesSyncNow(ctx context.Context) {
	o.triggerRulesSync(ctx)
}

func (o *Orchestrator) waitIngestReady(ctx context.Context, cameraID string, minFrames int) error {
	deadline := time.Now().Add(demoHealTimeout)
	var lastFrames int
	for time.Now().Before(deadline) {
		st, err := o.ai.CameraStatus(ctx, cameraID)
		if err == nil && st.Running && st.FramesProcessed >= minFrames {
			return nil
		}
		if err == nil {
			lastFrames = st.FramesProcessed
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(2 * time.Second):
		}
	}
	return fmt.Errorf("camera %s frames=%d need>=%d running", shortCamID(cameraID), lastFrames, minFrames)
}

func shortCamID(id string) string {
	if len(id) >= 8 {
		return id[:8]
	}
	return id
}
