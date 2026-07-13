package health

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/citevision/citevision-v2/backend/internal/demo"
	"github.com/citevision/citevision-v2/backend/internal/frigate"
	"github.com/citevision/citevision-v2/backend/internal/ingest"
)

// PlatformDeps aggregates probes for unified platform health.
type PlatformDeps struct {
	Checker *Checker
	AI      *ingest.AIClient
	Frigate *frigate.SyncService
	Demo    *demo.Service
}

// ComponentStatus is one subsystem health entry.
type ComponentStatus struct {
	Status string                 `json:"status"`
	Detail map[string]interface{} `json:"detail,omitempty"`
}

// PlatformHealth is the unified health payload.
type PlatformHealth struct {
	Status     string                     `json:"status"`
	CheckedAt  string                     `json:"checked_at"`
	Components map[string]ComponentStatus `json:"components"`
	Issues     []string                   `json:"issues,omitempty"`
}

// PlatformHandler returns GET /api/v1/system/health aggregator.
func PlatformHandler(deps PlatformDeps) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ctx, cancel := context.WithTimeout(r.Context(), 12*time.Second)
		defer cancel()

		ph := CollectPlatformHealth(ctx, deps)
		code := http.StatusOK
		if ph.Status == "down" {
			code = http.StatusServiceUnavailable
		} else if ph.Status == "degraded" {
			code = http.StatusOK // degraded but reachable
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(code)
		_ = json.NewEncoder(w).Encode(ph)
	}
}

// CollectPlatformHealth aggregates all subsystem probes.
func CollectPlatformHealth(ctx context.Context, deps PlatformDeps) PlatformHealth {
	now := time.Now().UTC().Format(time.RFC3339)
	comps := map[string]ComponentStatus{}
	var issues []string
	criticalDown := 0
	degraded := 0

	// Backend liveness
	comps["backend"] = ComponentStatus{Status: "ok"}

	// Postgres + Redis
	if deps.Checker != nil {
		if err := deps.Checker.PingPostgres(ctx); err != nil {
			comps["postgres"] = ComponentStatus{Status: "down", Detail: map[string]interface{}{"error": err.Error()}}
			issues = append(issues, "postgres down")
			criticalDown++
		} else {
			comps["postgres"] = ComponentStatus{Status: "ok"}
		}
		if err := deps.Checker.PingRedis(ctx); err != nil {
			comps["redis"] = ComponentStatus{Status: "down", Detail: map[string]interface{}{"error": err.Error()}}
			issues = append(issues, "redis down")
			criticalDown++
		} else {
			comps["redis"] = ComponentStatus{Status: "ok"}
		}
	}

	// AI engine
	if deps.AI != nil {
		h, err := deps.AI.FetchHealth(ctx)
		if err != nil {
			comps["ai_engine"] = ComponentStatus{Status: "down", Detail: map[string]interface{}{"error": err.Error()}}
			issues = append(issues, "ai_engine unreachable")
			criticalDown++
		} else {
			st := "ok"
			if h["models_all_ok"] != "true" && h["models_all_ok"] != "True" {
				st = "degraded"
				issues = append(issues, "ai models not all ok")
				degraded++
			}
			detail := map[string]interface{}{}
			for _, k := range []string{"yolo_loaded", "plate_loaded", "face_loaded", "driver_phone_model_loaded", "seatbelt_model_loaded", "models_all_ok", "registry_version"} {
				if v, ok := h[k]; ok {
					detail[k] = v
				}
			}
			comps["ai_engine"] = ComponentStatus{Status: st, Detail: detail}
		}
	}

	// Rules engine
	rulesURL := envStr("RULES_ENGINE_URL", "http://127.0.0.1:8010")
	if st, detail, err := probeJSON(ctx, rulesURL+"/health"); err != nil {
		comps["rules_engine"] = ComponentStatus{Status: "down", Detail: map[string]interface{}{"error": err.Error()}}
		issues = append(issues, "rules_engine unreachable")
		criticalDown++
	} else {
		status := "ok"
		if ar, ok := detail["active_rules"]; ok {
			if n, _ := toInt(ar); n == 0 {
				status = "degraded"
				issues = append(issues, "rules_engine active_rules=0")
				degraded++
			}
		}
		comps["rules_engine"] = ComponentStatus{Status: status, Detail: st}
	}

	// Frigate
	if deps.Frigate != nil && deps.Frigate.Enabled() {
		fs := deps.Frigate.Status(ctx)
		st := "ok"
		if reach, _ := fs["reachable"].(bool); !reach {
			st = "degraded"
			issues = append(issues, "frigate unreachable")
			degraded++
		}
		if age, ok := deps.Frigate.YoungestEventAgeSec(ctx); ok && age > 25 {
			st = "degraded"
			fs["youngest_event_age_sec"] = age
			issues = append(issues, "frigate events stale")
			degraded++
		}
		comps["frigate"] = ComponentStatus{Status: st, Detail: fs}
	} else {
		comps["frigate"] = ComponentStatus{Status: "ok", Detail: map[string]interface{}{"enabled": false}}
	}

	// MinIO
	minioURL := envStr("MINIO_ENDPOINT", "http://127.0.0.1:9003")
	if err := probeHead(ctx, minioURL+"/minio/health/live"); err != nil {
		comps["minio"] = ComponentStatus{Status: "degraded", Detail: map[string]interface{}{"error": err.Error()}}
		issues = append(issues, "minio degraded")
		degraded++
	} else {
		comps["minio"] = ComponentStatus{Status: "ok"}
	}

	// go2rtc
	go2URL := envStr("GO2RTC_URL", "http://127.0.0.1:1984")
	if _, detail, err := probeJSON(ctx, go2URL+"/api"); err != nil {
		comps["go2rtc"] = ComponentStatus{Status: "degraded", Detail: map[string]interface{}{"error": err.Error()}}
		degraded++
	} else {
		comps["go2rtc"] = ComponentStatus{Status: "ok", Detail: detail}
	}

	// Disk usage (WSL paths when available)
	diskDetail := diskUsageSummary()
	if pct, ok := diskDetail["used_percent"].(float64); ok && pct > 80 {
		comps["disk"] = ComponentStatus{Status: "degraded", Detail: diskDetail}
		issues = append(issues, "disk usage above 80%")
		degraded++
	} else {
		comps["disk"] = ComponentStatus{Status: "ok", Detail: diskDetail}
	}

	// Retention stats
	retDetail := map[string]interface{}{
		"demo_retention_minutes": demo.RetentionMinutes,
		"max_demo_events":        demo.MaxDemoEventsTotal,
	}
	if deps.Demo != nil {
		retDetail["last_disk_purge_at"] = deps.Demo.LastDiskPurgeAt()
	}
	comps["retention"] = ComponentStatus{Status: "ok", Detail: retDetail}

	overall := "ok"
	if criticalDown > 0 {
		overall = "down"
	} else if degraded > 0 {
		overall = "degraded"
	}
	return PlatformHealth{
		Status:     overall,
		CheckedAt:  now,
		Components: comps,
		Issues:     issues,
	}
}

func probeJSON(ctx context.Context, url string) (map[string]interface{}, map[string]interface{}, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, nil, err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 256))
		return nil, nil, errStatus(resp.StatusCode, string(body))
	}
	var out map[string]interface{}
	_ = json.NewDecoder(resp.Body).Decode(&out)
	if out == nil {
		out = map[string]interface{}{"status": "ok"}
	}
	return out, out, nil
}

func probeHead(ctx context.Context, url string) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodHead, url, nil)
	if err != nil {
		return err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		// MinIO live endpoint may not support HEAD — try GET
		req2, _ := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
		resp2, err2 := http.DefaultClient.Do(req2)
		if err2 != nil {
			return err
		}
		defer resp2.Body.Close()
		if resp2.StatusCode >= 300 {
			return errStatus(resp2.StatusCode, "")
		}
		return nil
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return errStatus(resp.StatusCode, "")
	}
	return nil
}

type statusErr struct {
	code int
	msg  string
}

func (e statusErr) Error() string { return e.msg }

func errStatus(code int, msg string) error {
	if msg == "" {
		msg = http.StatusText(code)
	}
	return statusErr{code: code, msg: msg}
}

func envStr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func toInt(v interface{}) (int, bool) {
	switch t := v.(type) {
	case float64:
		return int(t), true
	case int:
		return t, true
	case json.Number:
		n, err := t.Int64()
		return int(n), err == nil
	case string:
		n, err := strconv.Atoi(strings.TrimSpace(t))
		return n, err == nil
	default:
		return 0, false
	}
}

func diskUsageSummary() map[string]interface{} {
	out := map[string]interface{}{}
	for _, path := range []string{"/", os.Getenv("FRIGATE_RECORDINGS_PATH")} {
		if path == "" {
			continue
		}
		if u, err := diskUsage(path); err == nil {
			out[path] = u
			if pct, ok := u["used_percent"].(float64); ok {
				out["used_percent"] = pct
			}
		}
	}
	return out
}
