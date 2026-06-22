package mqttsub

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"sync"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"

	"github.com/citevision/citevision-v2/backend/internal/alerts"
	"github.com/citevision/citevision-v2/backend/internal/org"
	"github.com/citevision/citevision-v2/backend/internal/routing"
	"github.com/citevision/citevision-v2/backend/internal/ws"
)

type AlertHandler func(alert *alerts.CreateAlertRequest)

type Subscriber struct {
	client  mqtt.Client
	handler AlertHandler
	log     *slog.Logger
	mu      sync.Mutex
}

func New(broker string, handler AlertHandler, log *slog.Logger) *Subscriber {
	opts := mqtt.NewClientOptions().
		AddBroker(broker).
		SetClientID("citevision-backend").
		SetAutoReconnect(true).
		SetConnectRetry(true).
		SetConnectRetryInterval(5 * time.Second)
	return &Subscriber{
		client:  mqtt.NewClient(opts),
		handler: handler,
		log:     log,
	}
}

func (s *Subscriber) Start(ctx context.Context) {
	go func() {
		for {
			select {
			case <-ctx.Done():
				s.client.Disconnect(250)
				return
			default:
			}
			if !s.client.IsConnected() {
				token := s.client.Connect()
				token.Wait()
				if err := token.Error(); err != nil {
					s.log.Warn("mqtt connect failed, retrying", "error", err)
					time.Sleep(5 * time.Second)
					continue
				}
				token = s.client.Subscribe("cv/alerts/#", 1, s.onMessage)
				token.Wait()
				if err := token.Error(); err != nil {
					s.log.Warn("mqtt subscribe failed", "error", err)
				} else {
					s.log.Info("mqtt subscribed", "topic", "cv/alerts/#")
				}
			}
			time.Sleep(10 * time.Second)
		}
	}()
}

func (s *Subscriber) onMessage(_ mqtt.Client, msg mqtt.Message) {
	var payload map[string]interface{}
	if err := json.Unmarshal(msg.Payload(), &payload); err != nil {
		s.log.Warn("invalid mqtt alert payload", "error", err)
		return
	}
	req := alerts.CreateAlertRequest{
		Title:    stringField(payload, "title", "Alerte"),
		Message:  stringField(payload, "message", ""),
		Severity: stringField(payload, "severity", "medium"),
	}
	if orgStr, ok := payload["org_id"].(string); ok && orgStr != "" {
		if id, err := parseUUID(orgStr); err == nil {
			req.OrgID = id
		}
	}
	if ruleStr, ok := payload["rule_id"].(string); ok && ruleStr != "" {
		if id, err := parseUUID(ruleStr); err == nil {
			req.RuleID = &id
		}
	}
	if req.OrgID.String() == "00000000-0000-0000-0000-000000000000" {
		s.log.Warn("mqtt alert missing org_id, skipping")
		return
	}
	if meta, ok := payload["metadata"].(map[string]interface{}); ok {
		b, _ := json.Marshal(mergeProofFields(payload, meta))
		req.Metadata = b
	} else {
		b, _ := json.Marshal(mergeProofFields(payload, payload))
		req.Metadata = b
	}
	s.handler(&req)
}

func stringField(m map[string]interface{}, key, fallback string) string {
	if v, ok := m[key].(string); ok && v != "" {
		return v
	}
	return fallback
}

func mergeProofFields(top, meta map[string]interface{}) map[string]interface{} {
	out := map[string]interface{}{}
	for k, v := range meta {
		out[k] = v
	}
	for _, k := range []string{"bbox", "confidence", "track_id", "zone_id", "line_id",
		"plate_number", "face_label", "event_type", "speed_kmh", "direction", "clip_path", "camera_id", "action_log", "class_name", "evidence", "package"} {
		if v, ok := top[k]; ok && v != nil {
			out[k] = v
		}
	}
	if p, ok := top["payload"].(map[string]interface{}); ok {
		if _, has := out["payload"]; !has {
			out["payload"] = p
		}
	}
	return out
}

type Broadcaster struct {
	Hub     *ws.Hub
	Alerts  *alerts.Service
	Routing *routing.Service
	Orgs    *org.Service
	OnAlert func(*alerts.CreateAlertRequest)
}

func (b *Broadcaster) HandleMQTTAlert(req *alerts.CreateAlertRequest) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	a, err := b.Alerts.CreateAlert(ctx, *req)
	if err != nil {
		if errors.Is(err, alerts.ErrIncompleteEvidence) {
			return
		}
		return
	}
	b.Hub.Broadcast(map[string]interface{}{
		"type":    "alert",
		"alert":   a,
		"message": a.Title,
	})
	if b.Routing != nil && b.Orgs != nil {
		go b.Routing.DispatchAuto(context.Background(), b.Orgs, b.Alerts, req.OrgID, a.ID)
	}
	if b.OnAlert != nil {
		b.OnAlert(req)
	}
}
