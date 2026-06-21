package health

import (
	"context"
	"net/http"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"

	redisstore "github.com/citevision/citevision-v2/backend/internal/redis"
)

var (
	httpRequestsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{Name: "citevision_v2_http_requests_total", Help: "Total HTTP requests"},
		[]string{"method", "path", "status"},
	)
	httpRequestDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{Name: "citevision_v2_http_request_duration_seconds", Help: "HTTP request duration"},
		[]string{"method", "path"},
	)

	// Business metrics — observable KPIs for dashboards/alerting.
	alertsCreatedTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{Name: "citevision_v2_alerts_created_total", Help: "Alerts created"},
		[]string{"severity"},
	)
	webhookDeliveriesTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{Name: "citevision_v2_webhook_deliveries_total", Help: "Outbound webhook delivery outcomes"},
		[]string{"preset", "result"},
	)
	// DLQ size gauge — alert when this grows (deliveries are failing).
	webhookDLQSize = promauto.NewGauge(
		prometheus.GaugeOpts{Name: "citevision_v2_webhook_dlq_size", Help: "Current webhook dead-letter queue size (entries)"},
	)
)

// RecordAlertCreated increments the alert counter by severity.
func RecordAlertCreated(severity string) {
	if severity == "" {
		severity = "unknown"
	}
	alertsCreatedTotal.WithLabelValues(severity).Inc()
}

// RecordWebhookDelivery records an outbound webhook outcome ("success"/"failure").
func RecordWebhookDelivery(preset, result string) {
	if preset == "" {
		preset = "generic"
	}
	webhookDeliveriesTotal.WithLabelValues(preset, result).Inc()
}

// SetWebhookDLQSize publishes the current DLQ depth for alerting on growth.
func SetWebhookDLQSize(n float64) {
	webhookDLQSize.Set(n)
}

// IncWebhookDLQSize bumps the DLQ depth by one (a delivery was dead-lettered).
func IncWebhookDLQSize() {
	webhookDLQSize.Inc()
}

type Checker struct {
	pool    *pgxpool.Pool
	redis   *redisstore.Client
}

func NewChecker(pool *pgxpool.Pool, redis *redisstore.Client) *Checker {
	return &Checker{pool: pool, redis: redis}
}

func (c *Checker) Live(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(`{"status":"ok"}`))
}

func (c *Checker) Ready(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()

	if err := c.pool.Ping(ctx); err != nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		_, _ = w.Write([]byte(`{"status":"degraded","database":"down"}`))
		return
	}
	if c.redis != nil {
		if err := c.redis.Ping(ctx); err != nil {
			w.WriteHeader(http.StatusServiceUnavailable)
			_, _ = w.Write([]byte(`{"status":"degraded","redis":"down"}`))
			return
		}
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(`{"status":"ok","database":"ok","redis":"ok"}`))
}

func MetricsHandler() http.Handler {
	return promhttp.Handler()
}

func RecordRequest(method, path string, status int, duration time.Duration) {
	httpRequestsTotal.WithLabelValues(method, path, http.StatusText(status)).Inc()
	httpRequestDuration.WithLabelValues(method, path).Observe(duration.Seconds())
}
