package health

import (
	"context"
	"net/http"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
	httpRequestsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{Name: "citevision_http_requests_total", Help: "Total HTTP requests"},
		[]string{"method", "path", "status"},
	)
	httpRequestDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{Name: "citevision_http_request_duration_seconds", Help: "HTTP request duration"},
		[]string{"method", "path"},
	)
)

type Checker struct {
	pool *pgxpool.Pool
}

func NewChecker(pool *pgxpool.Pool) *Checker {
	return &Checker{pool: pool}
}

type Status struct {
	Status   string            `json:"status"`
	Database string            `json:"database"`
	Uptime   string            `json:"uptime,omitempty"`
	Checks   map[string]string `json:"checks,omitempty"`
}

var startTime = time.Now()

func (c *Checker) Live(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(`{"status":"ok"}`))
}

func (c *Checker) Ready(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()

	dbStatus := "ok"
	if err := c.pool.Ping(ctx); err != nil {
		dbStatus = "down"
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = w.Write([]byte(`{"status":"degraded","database":"down"}`))
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(`{"status":"ok","database":"` + dbStatus + `"}`))
}

func MetricsHandler() http.Handler {
	return promhttp.Handler()
}

func RecordRequest(method, path string, status int, duration time.Duration) {
	httpRequestsTotal.WithLabelValues(method, path, http.StatusText(status)).Inc()
	httpRequestDuration.WithLabelValues(method, path).Observe(duration.Seconds())
}
