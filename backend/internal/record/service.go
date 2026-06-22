package record

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/citevision/citevision-v2/backend/internal/camera"
)

type Service struct {
	pool    *pgxpool.Pool
	cameras *camera.Service
	outDir  string
}

func NewService(pool *pgxpool.Pool, cameras *camera.Service) *Service {
	dir := os.Getenv("CLIP_OUTPUT_DIR")
	if dir == "" {
		dir = filepath.Join(".", "data", "clips")
	}
	_ = os.MkdirAll(dir, 0o755)
	return &Service{pool: pool, cameras: cameras, outDir: dir}
}

type ClipRequest struct {
	CameraID       uuid.UUID
	DurationSec    int
	RuleID         string
	TriggerPayload map[string]interface{}
}

type ClipResult struct {
	Path      string `json:"path"`
	ClipPath  string `json:"clip_path"`
	Duration  int    `json:"duration_sec"`
	CameraID  string `json:"camera_id"`
	CreatedAt string `json:"created_at"`
}

func (s *Service) RecordClip(ctx context.Context, orgID uuid.UUID, req ClipRequest) (*ClipResult, error) {
	if req.DurationSec <= 0 {
		req.DurationSec = 30
	}
	if req.DurationSec > 120 {
		req.DurationSec = 120
	}
	rtsp, err := s.cameras.BuildRTSP(ctx, orgID, req.CameraID)
	if err != nil || rtsp == "" {
		return nil, fmt.Errorf("rtsp unavailable")
	}
	filename := fmt.Sprintf("%s_%d.mp4", req.CameraID.String(), time.Now().Unix())
	outPath := filepath.Join(s.outDir, filename)
	cmd := exec.CommandContext(ctx, "ffmpeg",
		"-y", "-rtsp_transport", "tcp",
		"-i", rtsp,
		"-t", fmt.Sprintf("%d", req.DurationSec),
		"-c", "copy",
		outPath,
	)
	if out, err := cmd.CombinedOutput(); err != nil {
		return nil, fmt.Errorf("ffmpeg: %w (%s)", err, string(out))
	}
	return &ClipResult{
		Path:      outPath,
		ClipPath:  outPath,
		Duration:  req.DurationSec,
		CameraID:  req.CameraID.String(),
		CreatedAt: time.Now().UTC().Format(time.RFC3339),
	}, nil
}
