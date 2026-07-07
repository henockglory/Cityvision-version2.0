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

	"github.com/citevision/citevision-v2/backend/internal/demo"
	"github.com/citevision/citevision-v2/backend/internal/events"
	"github.com/citevision/citevision-v2/backend/internal/evidence"
)

type EventIngestor struct {
	pool    *pgxpool.Pool
	events  *events.Service
	demo    *demo.Service
	log     *slog.Logger
	client  mqtt.Client
	orgByCam map[string]uuid.UUID
}

func NewEventIngestor(pool *pgxpool.Pool, eventsSvc *events.Service, demoSvc *demo.Service, broker string, log *slog.Logger) *EventIngestor {
	e := &EventIngestor{
		pool:     pool,
		events:   eventsSvc,
		demo:     demoSvc,
		log:      log,
		orgByCam: make(map[string]uuid.UUID),
	}
	opts := mqtt.NewClientOptions().
		AddBroker(broker).
		SetClientID("citevision-event-ingestor").
		SetAutoReconnect(true).
		SetConnectRetry(true).
		SetConnectRetryInterval(5 * time.Second)
	opts.SetOnConnectHandler(func(_ mqtt.Client) {
		token := e.client.Subscribe("cv/events/#", 1, e.onMessage)
		token.Wait()
		if err := token.Error(); err != nil {
			e.log.Warn("event ingestor subscribe failed", "error", err)
		} else {
			e.log.Info("event ingestor subscribed", "topic", "cv/events/#")
		}
	})
	e.client = mqtt.NewClient(opts)
	return e
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

	var camID *uuid.UUID
	if id, err := uuid.Parse(cameraIDStr); err == nil {
		camID = &id
	}

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	if e.demo != nil && camID != nil && !e.demo.ShouldIngestDemoCamera(ctx, orgID, *camID) {
		return
	}

	severity := stringField(payload, "severity", "info")

	if e.demo != nil {
		e.demo.TagEventPayload(ctx, camID, payload)
	}
	raw, _ := json.Marshal(payload)
	evSnap := evidence.SnapshotFromPayload(payload)
	// Preserve the AI engine's event_id as DB primary key so evidence patches
	// (PatchEvidenceSnapshot) can locate the row by the same UUID.
	externalID, _ := payload["event_id"].(string)
	_, err := e.events.Ingest(ctx, events.IngestRequest{
		OrgID:            orgID,
		CameraID:         camID,
		EventType:        eventType,
		Severity:         severity,
		Payload:          raw,
		EvidenceSnapshot: evSnap,
		ExternalID:       externalID,
	})
	if err != nil {
		e.log.Warn("event ingest failed", "error", err, "type", eventType, "camera", cameraIDStr)
	}

	// Persistent line counter: every crossing increments the counter for its line.
	if eventType == "line_cross" {
		e.incrementLineCounter(ctx, orgID, camID, payload)
	}
}

// incrementLineCounter upserts the per-line crossing counter. Direction "in"/"out"
// bump the matching column; anything else still bumps the total.
// Increments both global (class_filter='') and per-class rows when class_name is set.
func (e *EventIngestor) incrementLineCounter(ctx context.Context, orgID uuid.UUID, camID *uuid.UUID, payload map[string]interface{}) {
	lineID := stringField(payload, "line_id", "")
	if lineID == "" {
		return
	}
	direction := strings.ToLower(stringField(payload, "direction", ""))
	className := stringField(payload, "class_name", "")
	inInc, outInc := 0, 0
	switch direction {
	case "in", "entry", "north", "up":
		inInc = 1
	case "out", "exit", "south", "down":
		outInc = 1
	}
	e.bumpLineCounter(ctx, orgID, camID, lineID, "", className, inInc, outInc, direction)
	if className != "" {
		e.bumpLineCounter(ctx, orgID, camID, lineID, className, className, inInc, outInc, direction)
	}
}

func (e *EventIngestor) bumpLineCounter(ctx context.Context, orgID uuid.UUID, camID *uuid.UUID, lineID, classFilter, lastClass string, inInc, outInc int, direction string) {
	_, err := e.pool.Exec(ctx, `
		INSERT INTO line_counters (org_id, camera_id, line_id, class_filter, count_in, count_out, count_total, last_class, updated_at)
		VALUES ($1,$2,$3,$4,$5,$6,1,$7,NOW())
		ON CONFLICT (org_id, camera_id, line_id, class_filter) DO UPDATE SET
			count_in = line_counters.count_in + EXCLUDED.count_in,
			count_out = line_counters.count_out + EXCLUDED.count_out,
			count_total = line_counters.count_total + 1,
			last_class = EXCLUDED.last_class,
			updated_at = NOW()`,
		orgID, camID, lineID, classFilter, inInc, outInc, lastClass,
	)
	if err != nil {
		e.log.Debug("line counter increment failed", "error", err, "line", lineID, "class_filter", classFilter)
	} else {
		e.log.Info("line crossing counted", "line", lineID, "class_filter", classFilter, "direction", direction, "class", lastClass)
	}
}
