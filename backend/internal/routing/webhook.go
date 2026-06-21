package routing

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/google/uuid"

	"github.com/citevision/citevision-v2/backend/internal/health"
)

const (
	defaultWebhookTimeout = 10 * time.Second
	defaultMaxAttempts    = 3
	defaultBackoffBase    = 500 * time.Millisecond
)

// WebhookDeliveryOptions controls retry and envelope behaviour.
type WebhookDeliveryOptions struct {
	MaxAttempts int
	Timeout     time.Duration
	CloudEvents bool
	DLQPath     string
}

func defaultWebhookOptions() WebhookDeliveryOptions {
	opts := WebhookDeliveryOptions{
		MaxAttempts: defaultMaxAttempts,
		Timeout:     defaultWebhookTimeout,
		CloudEvents: true,
		DLQPath:     "",
	}
	if v := os.Getenv("WEBHOOK_MAX_ATTEMPTS"); v != "" {
		if n, err := parsePositiveInt(v); err == nil {
			opts.MaxAttempts = n
		}
	}
	if os.Getenv("WEBHOOK_CLOUDEVENTS") == "0" {
		opts.CloudEvents = false
	}
	if p := os.Getenv("WEBHOOK_DLQ_PATH"); p != "" {
		opts.DLQPath = p
	} else {
		opts.DLQPath = filepath.Join("logs", "routing-dlq.jsonl")
	}
	return opts
}

func parsePositiveInt(s string) (int, error) {
	var n int
	_, err := fmt.Sscanf(s, "%d", &n)
	if err != nil || n < 1 {
		return 0, fmt.Errorf("invalid int")
	}
	return n, nil
}

func wrapCloudEvents(payload map[string]interface{}) map[string]interface{} {
	alertID, _ := payload["alert_id"].(string)
	orgID, _ := payload["org_id"].(string)
	ts, _ := payload["timestamp"].(string)
	if ts == "" {
		ts = time.Now().UTC().Format(time.RFC3339)
	}
	ceID := alertID
	if ceID == "" {
		ceID = uuid.NewString()
	}
	return map[string]interface{}{
		"specversion":     "1.0",
		"type":            "com.citevision.alert.v1",
		"source":          fmt.Sprintf("/orgs/%s/citevision", orgID),
		"id":              ceID,
		"time":            ts,
		"datacontenttype": "application/json",
		"data":            payload,
	}
}

func httpNewPost(url string, body []byte, deliveryID string) (*http.Request, error) {
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-CiteVision-Delivery-Id", deliveryID)
	req.Header.Set("Ce-Specversion", "1.0")
	req.Header.Set("Ce-Type", "com.citevision.alert.v1")
	if sig := signBody(body); sig != "" {
		req.Header.Set("X-CiteVision-Signature", sig)
	}
	return req, nil
}

func doHTTP(req *http.Request, timeout time.Duration) (int, error) {
	client := &http.Client{Timeout: timeout}
	resp, err := client.Do(req)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, resp.Body)
	if resp.StatusCode >= 400 {
		return resp.StatusCode, fmt.Errorf("webhook HTTP %d", resp.StatusCode)
	}
	return resp.StatusCode, nil
}

func appendDLQ(path string, entry map[string]interface{}) {
	if path == "" {
		return
	}
	_ = os.MkdirAll(filepath.Dir(path), 0o755)
	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return
	}
	defer f.Close()
	b, _ := json.Marshal(entry)
	_, _ = f.Write(append(b, '\n'))
}

// PostWebhook delivers payload with retries, optional CloudEvents envelope, DLQ on failure.
func PostWebhook(url string, payload map[string]interface{}) error {
	return PostWebhookPreset(url, PresetGeneric, payload)
}

// PostWebhookPreset adapts the payload to the destination preset (Slack/Teams/
// Discord/n8n/Make/Zapier) before delivering with SSRF validation, HMAC signing,
// retries and DLQ on failure.
func PostWebhookPreset(url, preset string, payload map[string]interface{}) error {
	if err := ValidateWebhookURL(url); err != nil {
		return err
	}
	opts := defaultWebhookOptions()
	bodyPayload, useCloudEvents := transformForPreset(preset, payload)
	if useCloudEvents && opts.CloudEvents {
		bodyPayload = wrapCloudEvents(bodyPayload)
	}
	body, err := json.Marshal(bodyPayload)
	if err != nil {
		return err
	}
	deliveryID := uuid.NewString()
	var lastErr error
	for attempt := 1; attempt <= opts.MaxAttempts; attempt++ {
		req, err := httpNewPost(url, body, deliveryID)
		if err != nil {
			lastErr = err
			break
		}
		status, err := doHTTP(req, opts.Timeout)
		if err == nil {
			health.RecordWebhookDelivery(preset, "success")
			return nil
		}
		lastErr = err
		if attempt < opts.MaxAttempts {
			sleep := time.Duration(attempt) * defaultBackoffBase
			time.Sleep(sleep)
		}
		_ = status
	}
	appendDLQ(opts.DLQPath, map[string]interface{}{
		"timestamp":   time.Now().UTC().Format(time.RFC3339),
		"delivery_id": deliveryID,
		"webhook_url": url,
		"attempts":    opts.MaxAttempts,
		"error":       lastErr.Error(),
		"payload":     bodyPayload,
	})
	health.RecordWebhookDelivery(preset, "failure")
	health.IncWebhookDLQSize()
	return lastErr
}

