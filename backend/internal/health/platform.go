package health

import (
	"context"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/citevision/citevision-v2/backend/internal/demo"
	"github.com/citevision/citevision-v2/backend/internal/frigate"
	"github.com/citevision/citevision-v2/backend/internal/ingest"
)

const probeBudget = 2 * time.Second

// probeHTTP is a short-timeout client so one hung Frigate/MinIO/go2rtc probe
// cannot pin /health/platform at the handler deadline (12s) and flap the UI.
var probeHTTP = &http.Client{
	Timeout: probeBudget,
	Transport: &http.Transport{
		DialContext:           (&net.Dialer{Timeout: 800 * time.Millisecond}).DialContext,
		ResponseHeaderTimeout: probeBudget,
		DisableKeepAlives:     true,
	},
}

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
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
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
	var mu sync.Mutex
	set := func(name string, cs ComponentStatus, issue string, crit, deg bool) {
		mu.Lock()
		defer mu.Unlock()
		comps[name] = cs
		if issue != "" {
			issues = append(issues, issue)
		}
		if crit {
			criticalDown++
		}
		if deg {
			degraded++
		}
	}

	comps["backend"] = ComponentStatus{Status: "ok"}

	var wg sync.WaitGroup
	run := func(fn func(context.Context)) {
		wg.Add(1)
		go func() {
			defer wg.Done()
			pctx, cancel := context.WithTimeout(ctx, probeBudget)
			defer cancel()
			fn(pctx)
		}()
	}

	if deps.Checker != nil {
		run(func(pctx context.Context) {
			if err := deps.Checker.PingPostgres(pctx); err != nil {
				set("postgres", ComponentStatus{Status: "down", Detail: map[string]interface{}{"error": err.Error()}}, "postgres down", true, false)
			} else {
				set("postgres", ComponentStatus{Status: "ok"}, "", false, false)
			}
		})
		run(func(pctx context.Context) {
			if err := deps.Checker.PingRedis(pctx); err != nil {
				set("redis", ComponentStatus{Status: "down", Detail: map[string]interface{}{"error": err.Error()}}, "redis down", true, false)
			} else {
				set("redis", ComponentStatus{Status: "ok"}, "", false, false)
			}
		})
	}

	if deps.AI != nil {
		run(func(pctx context.Context) {
			h, err := deps.AI.FetchHealth(pctx)
			if err != nil {
				set("ai_engine", ComponentStatus{Status: "down", Detail: map[string]interface{}{"error": err.Error()}}, "ai_engine unreachable", true, false)
				return
			}
			st := "ok"
			issue := ""
			deg := false
			if h["models_all_ok"] != "true" && h["models_all_ok"] != "True" {
				st = "degraded"
				issue = "ai models not all ok"
				deg = true
			}
			detail := map[string]interface{}{}
			for _, k := range []string{"yolo_loaded", "plate_loaded", "face_loaded", "driver_phone_model_loaded", "seatbelt_model_loaded", "models_all_ok", "registry_version"} {
				if v, ok := h[k]; ok {
					detail[k] = v
				}
			}
			set("ai_engine", ComponentStatus{Status: st, Detail: detail}, issue, false, deg)
		})
	}

	run(func(pctx context.Context) {
		rulesURL := envStr("RULES_ENGINE_URL", "http://127.0.0.1:8010")
		st, detail, err := probeJSON(pctx, rulesURL+"/health")
		if err != nil {
			set("rules_engine", ComponentStatus{Status: "down", Detail: map[string]interface{}{"error": err.Error()}}, "rules_engine unreachable", true, false)
			return
		}
		status := "ok"
		issue := ""
		deg := false
		if ar, ok := detail["active_rules"]; ok {
			if n, _ := toInt(ar); n == 0 {
				status = "degraded"
				issue = "rules_engine active_rules=0"
				deg = true
			}
		}
		mqttStaleSec := 120
		if v := envStr("RULES_MQTT_STALE_SEC", ""); v != "" {
			if n, ok := toInt(v); ok && n > 0 {
				mqttStaleSec = n
			}
		}
		connected := true
		if c, ok := detail["mqtt_connected"]; ok {
			switch t := c.(type) {
			case bool:
				connected = t
			case string:
				connected = strings.EqualFold(t, "true") || t == "1"
			}
		}
		ageSec := -1
		if a, ok := detail["last_mqtt_msg_age_sec"]; ok {
			if n, ok2 := toInt(a); ok2 {
				ageSec = n
			}
		}
		if !connected || (ageSec >= 0 && ageSec > mqttStaleSec) {
			status = "degraded"
			issue = "rules_engine mqtt_stale"
			deg = true
		}
		set("rules_engine", ComponentStatus{Status: status, Detail: st}, issue, false, deg)
	})

	run(func(pctx context.Context) {
		if deps.Frigate == nil || !deps.Frigate.Enabled() {
			set("frigate", ComponentStatus{Status: "ok", Detail: map[string]interface{}{"enabled": false}}, "", false, false)
			return
		}
		fs := deps.Frigate.Status(pctx)
		st := "ok"
		issue := ""
		deg := false
		if reach, _ := fs["reachable"].(bool); !reach {
			st = "degraded"
			issue = "frigate unreachable"
			deg = true
		}
		// Do not call YoungestEventAgeSec here: it walks cameras via Frigate HTTP
		// and turns a hung detector into a 12s /health/platform stall.
		set("frigate", ComponentStatus{Status: st, Detail: fs}, issue, false, deg)
	})

	run(func(pctx context.Context) {
		minioURL := envStr("MINIO_ENDPOINT", "http://127.0.0.1:9003")
		if err := probeHead(pctx, minioURL+"/minio/health/live"); err != nil {
			set("minio", ComponentStatus{Status: "degraded", Detail: map[string]interface{}{"error": err.Error()}}, "minio degraded", false, true)
		} else {
			set("minio", ComponentStatus{Status: "ok"}, "", false, false)
		}
	})

	run(func(pctx context.Context) {
		go2URL := envStr("GO2RTC_URL", "http://127.0.0.1:1984")
		if _, detail, err := probeJSON(pctx, go2URL+"/api"); err != nil {
			set("go2rtc", ComponentStatus{Status: "degraded", Detail: map[string]interface{}{"error": err.Error()}}, "", false, true)
		} else {
			set("go2rtc", ComponentStatus{Status: "ok", Detail: detail}, "", false, false)
		}
	})

	wg.Wait()

	diskDetail := diskUsageSummary()
	if pct, ok := diskDetail["used_percent"].(float64); ok && pct > 80 {
		comps["disk"] = ComponentStatus{Status: "degraded", Detail: diskDetail}
		issues = append(issues, "disk usage above 80%")
		degraded++
	} else {
		comps["disk"] = ComponentStatus{Status: "ok", Detail: diskDetail}
	}

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
	resp, err := probeHTTP.Do(req)
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
	resp, err := probeHTTP.Do(req)
	if err != nil {
		// MinIO live endpoint may not support HEAD — try GET
		req2, _ := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
		resp2, err2 := probeHTTP.Do(req2)
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
