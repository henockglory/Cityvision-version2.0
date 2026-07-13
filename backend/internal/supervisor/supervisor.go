package supervisor

import (
	"context"
	"io"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/citevision/citevision-v2/backend/internal/health"
	"github.com/citevision/citevision-v2/backend/internal/ingest"
)

// Deps holds callbacks for platform repair playbooks.
type Deps struct {
	HealthDeps   health.PlatformDeps
	Orchestrator *ingest.Orchestrator
	BackendURL   string
	InternalKey  string
	Log          *slog.Logger
}

// Runner polls platform health and triggers repair when degraded.
type Runner struct {
	deps       Deps
	interval   time.Duration
	maxRetries int
}

func NewRunner(deps Deps) *Runner {
	if deps.Log == nil {
		deps.Log = slog.Default()
	}
	if deps.BackendURL == "" {
		deps.BackendURL = "http://127.0.0.1:8081"
	}
	return &Runner{deps: deps, interval: 30 * time.Second, maxRetries: 3}
}

// Start runs the supervisor loop until ctx is cancelled.
func (r *Runner) Start(ctx context.Context) {
	ticker := time.NewTicker(r.interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			r.tick(ctx)
		}
	}
}

func (r *Runner) tick(ctx context.Context) {
	tctx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	ph := health.CollectPlatformHealth(tctx, r.deps.HealthDeps)
	if ph.Status == "ok" {
		return
	}
	r.deps.Log.Warn("platform degraded", "status", ph.Status, "issues", ph.Issues)
	for attempt := 0; attempt < r.maxRetries; attempt++ {
		if err := r.Repair(tctx, ph.Issues); err != nil {
			r.deps.Log.Warn("supervisor repair failed", "attempt", attempt+1, "error", err)
		}
		ph = health.CollectPlatformHealth(tctx, r.deps.HealthDeps)
		if ph.Status == "ok" {
			r.deps.Log.Info("platform recovered after repair", "attempt", attempt+1)
			return
		}
		time.Sleep(5 * time.Second)
	}
}

// Repair executes playbooks for known issues.
func (r *Runner) Repair(ctx context.Context, issues []string) error {
	if r.deps.Orchestrator == nil {
		return nil
	}
	if len(issues) == 0 {
		r.deps.Orchestrator.TriggerRulesSyncNow(ctx)
		r.deps.Orchestrator.InvalidateConfigHashes()
		r.deps.Orchestrator.SyncNow(ctx)
		return nil
	}
	for _, issue := range issues {
		switch {
		case strings.Contains(issue, "rules_engine"):
			r.deps.Orchestrator.TriggerRulesSyncNow(ctx)
		case strings.Contains(issue, "ai_engine"):
			r.postInternal(ctx, "/api/v1/internal/ingest/resync-spatial", nil)
		case strings.Contains(issue, "frigate"):
			r.postInternal(ctx, "/api/v1/internal/ingest/frigate/rebuild", nil)
		case strings.Contains(issue, "disk"):
			r.postInternal(ctx, "/api/v1/internal/demo/repair-streams", nil)
		}
	}
	r.deps.Orchestrator.InvalidateConfigHashes()
	r.deps.Orchestrator.SyncNow(ctx)
	return nil
}

func (r *Runner) postInternal(ctx context.Context, path string, body io.Reader) {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(r.deps.BackendURL, "/")+path, body)
	if err != nil {
		return
	}
	if r.deps.InternalKey != "" {
		req.Header.Set("X-Internal-Key", r.deps.InternalKey)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return
	}
	resp.Body.Close()
}

// InternalKeyFromEnv reads the internal API key.
func InternalKeyFromEnv() string {
	return os.Getenv("INTERNAL_API_KEY")
}
