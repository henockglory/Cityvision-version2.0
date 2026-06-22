package mqttsub

import (
	"context"
	"encoding/json"
	"log/slog"
	"strings"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/citevision/citevision-v2/backend/internal/events"
	"github.com/citevision/citevision-v2/backend/internal/evidence"
)

type EventIngestor struct {
	pool    *pgxpool.Pool
	events  *events.Service
	log     *slog.Logger
	client  mqtt.Client
	orgByCam map[string]uuid.UUID
}

func NewEventIngestor(pool *pgxpool.Pool, eventsSvc *events.Service, broker string, log *slog.Logger) *EventIngestor {
	opts := mqtt.NewClientOptions().
		AddBroker(broker).
		SetClientID("citevision-event-ingestor").
		SetAutoReconnect(true).
		SetConnectRetry(true).
		SetConnectRetryInterval(5 * time.Second)
	return &EventIngestor{
		pool:     pool,
		events:   eventsSvc,
		log:      log,
		client:   mqtt.NewClient(opts),
		orgByCam: make(map[string]uuid.UUID),
	}
}

func (e *EventIngestor) Start(ctx context.Context) {
	e.refreshCameraOrgs(ctx)
	go func() {
		ticker := time.NewTicker(2 * time.Minute)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				e.client.Disconnect(250)
				return
			case <-ticker.C:
				e.refreshCameraOrgs(ctx)
			}
		}
	}()

	go func() {
		for {
			select {
			case <-ctx.Done():
				return
			default:
			}
			if !e.client.IsConnected() {
				token := e.client.Connect()
				token.Wait()
				if err := token.Error(); err != nil {
					e.log.Warn("event ingestor mqtt connect failed", "error", err)
					time.Sleep(5 * time.Second)
					continue
				}
				token = e.client.Subscribe("cv/events/#", 1, e.onMessage)
				token.Wait()
				if err := token.Error(); err != nil {
					e.log.Warn("event ingestor subscribe failed", "error", err)
				} else {
					e.log.Info("event ingestor subscribed", "topic", "cv/events/#")
				}
			}
			time.Sleep(10 * time.Second)
		}
	}()
}

func (e *EventIngestor) refreshCameraOrgs(ctx context.Context) {
	rows, err := e.pool.Query(ctx, `SELECT id, org_id FROM cameras WHERE is_active = TRUE`)
	if err != nil {
		return
	}
	defer rows.Close()
	m := make(map[string]uuid.UUID)
	for rows.Next() {
		var id, orgID uuid.UUID
		if err := rows.Scan(&id, &orgID); err != nil {
			continue
		}
		m[id.String()] = orgID
	}
	e.orgByCam = m
}

func (e *EventIngestor) onMessage(_ mqtt.Client, msg mqtt.Message) {
	var payload map[string]interface{}
	if err := json.Unmarshal(msg.Payload(), &payload); err != nil {
		return
	}

	eventType, _ := payload["event_type"].(string)
	if eventType == "" {
		if ev, ok := payload["event"].(string); ok {
			eventType = ev
		}
	}
	if eventType == "" {
		return
	}

	cameraIDStr := stringField(payload, "camera_id", "")
	if cameraIDStr == "" {
		parts := strings.Split(msg.Topic(), "/")
		if len(parts) >= 3 {
			cameraIDStr = parts[2]
		}
	}

	orgID := uuid.Nil
	if orgStr, ok := payload["org_id"].(string); ok && orgStr != "" {
		orgID, _ = uuid.Parse(orgStr)
	}
	if orgID == uuid.Nil && cameraIDStr != "" {
		orgID = e.orgByCam[cameraIDStr]
	}
	if orgID == uuid.Nil {
		return
	}

	severity := stringField(payload, "severity", "info")
	var camID *uuid.UUID
	if id, err := uuid.Parse(cameraIDStr); err == nil {
		camID = &id
	}

	raw, _ := json.Marshal(payload)
	evSnap := evidence.SnapshotFromPayload(payload)
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	_, err := e.events.Ingest(ctx, events.IngestRequest{
		OrgID:            orgID,
		CameraID:         camID,
		EventType:        eventType,
		Severity:         severity,
		Payload:          raw,
		EvidenceSnapshot: evSnap,
	})
	if err != nil {
		e.log.Debug("event ingest failed", "error", err, "type", eventType)
	}
}
