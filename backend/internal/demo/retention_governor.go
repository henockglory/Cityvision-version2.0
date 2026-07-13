package demo

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"time"
)

// LastDiskPurgeAt returns RFC3339 timestamp of last disk purge pass.
func (s *Service) LastDiskPurgeAt() string {
	if s == nil {
		return ""
	}
	s.diskPurgeMu.RLock()
	defer s.diskPurgeMu.RUnlock()
	if s.lastDiskPurge.IsZero() {
		return ""
	}
	return s.lastDiskPurge.UTC().Format(time.RFC3339)
}

func (s *Service) recordDiskPurge() {
	s.diskPurgeMu.Lock()
	s.lastDiskPurge = time.Now()
	s.diskPurgeMu.Unlock()
}

// RetentionMinutesFromEnv returns unified retention window for DB and disk.
func RetentionMinutesFromEnv() int {
	if v := os.Getenv("DEMO_RETENTION_MINUTES"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			return n
		}
	}
	if v := os.Getenv("FRIGATE_DEMO_RETENTION_MIN"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			return n
		}
	}
	return RetentionMinutes
}

func (s *Service) runDiskPurgePass(ctx context.Context) {
	script := os.Getenv("DEMO_RETENTION_PURGE_SCRIPT")
	if script == "" {
		script = filepath.Join("scripts", "demo-retention-purge.sh")
	}
	if _, err := os.Stat(script); err != nil {
		return
	}
	minutes := RetentionMinutesFromEnv()
	cmd := exec.CommandContext(ctx, "bash", script)
	cmd.Env = append(os.Environ(), "FRIGATE_DEMO_RETENTION_MIN="+strconv.Itoa(minutes))
	if out, err := cmd.CombinedOutput(); err != nil {
		if s.log != nil {
			s.log.Warn("disk retention purge failed", "error", err, "output", string(out))
		}
		return
	}
	s.recordDiskPurge()
}
