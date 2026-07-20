package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	"github.com/citevision/citevision-v2/backend/internal/alerts"
	"github.com/citevision/citevision-v2/backend/internal/notify"
	"github.com/citevision/citevision-v2/backend/internal/record"
	"github.com/citevision/citevision-v2/backend/internal/routing"
)

func (a *API) InternalNotifyEmail(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	var req struct {
		To       string                 `json:"to"`
		Subject  string                 `json:"subject"`
		Message  string                 `json:"message"`
		Title    string                 `json:"title"`
		RuleName string                 `json:"rule_name"`
		Severity string                 `json:"severity"`
		Payload  map[string]interface{} `json:"payload"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if req.To == "" {
		writeError(w, http.StatusBadRequest, "to required")
		return
	}
	o, err := a.Orgs.Get(r.Context(), orgID)
	if err != nil {
		writeError(w, http.StatusNotFound, "org not found")
		return
	}
	cfg := notify.ParseSMTP(o.SMTPConfig)
	subject := req.Subject
	if subject == "" {
		subject = "Alerte CitéVision"
	}

	// Render premium HTML (with inline proof images) when a payload is supplied.
	if req.Payload != nil {
		html, inline := a.buildNotifyHTML(r.Context(), req.Title, req.RuleName, req.Severity, req.Payload)
		if html != "" {
			if err := notify.SendAlertHTML(cfg, req.To, subject, html, req.Message, inline); err != nil {
				if err2 := notify.SendAlert(cfg, req.To, subject, req.Message); err2 != nil {
					writeError(w, http.StatusInternalServerError, err2.Error())
					return
				}
			}
			writeJSON(w, http.StatusOK, map[string]string{"status": "sent"})
			return
		}
	}

	if err := notify.SendAlert(cfg, req.To, subject, req.Message); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "sent"})
}

// buildNotifyHTML renders a premium HTML alert email from a raw event payload,
// embedding up to 2 proof images inline (CID) when the evidence store is available.
func (a *API) buildNotifyHTML(ctx context.Context, title, ruleName, severity string, payload map[string]interface{}) (string, []notify.InlineImage) {
	sev := strings.ToLower(severity)
	switch sev {
	case "critical", "warning", "info":
	default:
		sev = "warning"
	}
	if title == "" {
		if ruleName != "" {
			title = ruleName
		} else {
			title = "Alerte CitéVision"
		}
	}
	str := func(k string) string {
		if v, ok := payload[k].(string); ok {
			return v
		}
		return ""
	}
	data := notify.AlertEmailData{
		Title:      title,
		RuleName:   ruleName,
		Severity:   sev,
		CameraName: str("camera_id"),
		Plate:      str("plate_number"),
		FaceLabel:  str("face_label"),
		EventType:  str("event_type"),
		MailHogURL: os.Getenv("MAILHOG_PUBLIC_URL"),
	}
	if sp, ok := payload["speed_kmh"]; ok && sp != nil {
		data.SpeedKmh = fmt.Sprintf("%v", sp)
	}
	if dir := str("direction"); dir != "" {
		data.Details = append(data.Details, notify.EmailDetail{Label: "Direction", Value: dir})
	}

	var inline []notify.InlineImage
	pkg := extractPackage(payload)
	if pkg != nil {
		if clip, ok := pkg["clip"].(map[string]interface{}); ok {
			if u, ok := clip["url"].(string); ok {
				data.ClipURL = u
			}
		}
		if imgs, ok := pkg["images"].([]interface{}); ok && a.Evidence != nil && a.Evidence.Available() {
			n := 0
			for _, raw := range imgs {
				if n >= 2 {
					break
				}
				im, ok := raw.(map[string]interface{})
				if !ok {
					continue
				}
				key, _ := im["asset_id"].(string)
				if key == "" {
					continue
				}
				b, ct, err := a.Evidence.GetObjectBytes(ctx, key)
				if err != nil || len(b) == 0 {
					continue
				}
				cid := fmt.Sprintf("proof%d", n+1)
				label, _ := im["label"].(string)
				if label == "" {
					label = "Preuve " + cid
				}
				data.Images = append(data.Images, notify.EmailImage{CID: cid, Label: label})
				inline = append(inline, notify.InlineImage{CID: cid, ContentType: ct, Data: b})
				n++
			}
		}
	}

	html, err := notify.RenderAlertEmail(data)
	if err != nil {
		return "", nil
	}
	return html, inline
}

// extractPackage finds an evidence package within a payload (top-level or under "evidence").
func extractPackage(payload map[string]interface{}) map[string]interface{} {
	if pkg, ok := payload["package"].(map[string]interface{}); ok {
		return pkg
	}
	if ev, ok := payload["evidence"].(map[string]interface{}); ok {
		if pkg, ok := ev["package"].(map[string]interface{}); ok {
			return pkg
		}
	}
	return nil
}

func (a *API) InternalRecordClip(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	if a.Record == nil {
		writeError(w, http.StatusServiceUnavailable, "record service unavailable")
		return
	}
	var req struct {
		CameraID       string                 `json:"camera_id"`
		DurationSec    int                    `json:"duration_sec"`
		RuleID         string                 `json:"rule_id"`
		TriggerPayload map[string]interface{} `json:"trigger_payload"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	camID, err := uuid.Parse(req.CameraID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid camera_id")
		return
	}
	result, err := a.Record.RecordClip(r.Context(), orgID, record.ClipRequest{
		CameraID:       camID,
		DurationSec:    req.DurationSec,
		RuleID:         req.RuleID,
		TriggerPayload: req.TriggerPayload,
	})
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (a *API) InternalCreateIncident(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	var req struct {
		Title       string                 `json:"title"`
		Description string                 `json:"description"`
		Severity    string                 `json:"severity"`
		SiteID      *string                `json:"site_id"`
		Metadata    map[string]interface{} `json:"metadata"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if req.Title == "" {
		req.Title = "Incident règle"
	}
	var siteID *uuid.UUID
	if req.SiteID != nil && *req.SiteID != "" {
		if id, err := uuid.Parse(*req.SiteID); err == nil {
			siteID = &id
		}
	}
	meta, _ := json.Marshal(req.Metadata)
	inc, err := a.Alerts.CreateIncident(r.Context(), alerts.CreateIncidentRequest{
		OrgID: orgID, SiteID: siteID, Title: req.Title,
		Description: req.Description, Severity: req.Severity, Metadata: meta,
	})
	if err != nil {
		writeError(w, http.StatusInternalServerError, "incident create failed")
		return
	}
	writeJSON(w, http.StatusCreated, inc)
}

func (a *API) InternalArchiveAlert(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	var req struct {
		AlertID          string                 `json:"alert_id"`
		Comment          string                 `json:"comment"`
		EvidenceSnapshot map[string]interface{} `json:"evidence_snapshot"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	alertID, err := uuid.Parse(req.AlertID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid alert_id")
		return
	}
	ev, _ := json.Marshal(req.EvidenceSnapshot)
	a2, err := a.Alerts.ArchiveAlert(r.Context(), orgID, alertID, alerts.ArchiveRequest{
		Comment: req.Comment, EvidenceSnapshot: ev,
	})
	if err != nil {
		writeError(w, http.StatusInternalServerError, "archive failed")
		return
	}
	writeJSON(w, http.StatusOK, a2)
}

func (a *API) InternalIncrementRuleCounter(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	var req struct {
		RuleID        string `json:"rule_id"`
		Delta         int    `json:"delta"`
		LastEventType string `json:"last_event_type"`
		LastClass     string `json:"last_class"`
		LastZoneID    string `json:"last_zone_id"`
		LastLineID    string `json:"last_line_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	ruleID, err := uuid.Parse(req.RuleID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid rule_id")
		return
	}
	meta := &alerts.RuleCounterMeta{
		LastEventType: req.LastEventType,
		LastClass:     req.LastClass,
		LastZoneID:    req.LastZoneID,
		LastLineID:    req.LastLineID,
	}
	if err := a.Alerts.IncrementRuleCounter(r.Context(), orgID, ruleID, req.Delta, meta); err != nil {
		writeError(w, http.StatusInternalServerError, "counter failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (a *API) InternalEvidenceRequest(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	if a.AI == nil {
		writeError(w, http.StatusServiceUnavailable, "ai client unavailable")
		return
	}
	var req struct {
		CameraID string                 `json:"camera_id"`
		Event    map[string]interface{} `json:"event"`
		Evidence map[string]interface{} `json:"evidence"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if req.CameraID == "" {
		writeError(w, http.StatusBadRequest, "camera_id required")
		return
	}
	payload := map[string]interface{}{
		"org_id":   orgID.String(),
		"event":    req.Event,
		"evidence": req.Evidence,
	}
	out, err := a.AI.RequestEvidenceCapture(r.Context(), req.CameraID, payload)
	if err != nil {
		writeError(w, http.StatusBadGateway, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, out)
}

func (a *API) InternalWebhook(w http.ResponseWriter, r *http.Request) {
	var req struct {
		URL     string                 `json:"url"`
		Payload map[string]interface{} `json:"payload"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	url := req.URL
	if url == "" {
		url = os.Getenv("WEBHOOK_LOCAL_URL")
	}
	if url == "" {
		writeError(w, http.StatusBadRequest, "url required")
		return
	}
	// Route through the hardened delivery path: SSRF validation, signing,
	// retries with backoff and DLQ on failure (unifies the two webhook paths).
	if err := routing.PostWebhook(url, req.Payload); err != nil {
		writeError(w, http.StatusBadGateway, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"status": "sent"})
}

func (a *API) InternalArchiveStaleAlerts(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	var req struct {
		RuleID           string                 `json:"rule_id"`
		OlderThanMin     int                    `json:"older_than_min"`
		Comment          string                 `json:"comment"`
		EvidenceSnapshot map[string]interface{} `json:"evidence_snapshot"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	ruleID, err := uuid.Parse(req.RuleID)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid rule_id")
		return
	}
	ev, _ := json.Marshal(req.EvidenceSnapshot)
	n, err := a.Alerts.ArchiveStaleByRule(r.Context(), orgID, ruleID, req.OlderThanMin, req.Comment, ev)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "archive stale failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"status": "archived", "count": n})
}

func (a *API) InternalResyncSpatial(w http.ResponseWriter, r *http.Request) {
	if a.Orchestrator == nil {
		writeError(w, http.StatusServiceUnavailable, "orchestrator unavailable")
		return
	}
	a.Orchestrator.InvalidateConfigHashes()
	a.Orchestrator.SyncNow(r.Context())
	writeJSON(w, http.StatusOK, map[string]string{"status": "synced"})
}

func (a *API) InternalDebugSpatialConfig(w http.ResponseWriter, r *http.Request) {
	if a.Orchestrator == nil || a.Cameras == nil {
		writeError(w, http.StatusServiceUnavailable, "orchestrator unavailable")
		return
	}
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	cameraID, err := uuid.Parse(chi.URLParam(r, "cameraID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid camera id")
		return
	}
	if _, err := a.Cameras.Get(r.Context(), orgID, cameraID); err != nil {
		writeError(w, http.StatusNotFound, "camera not found")
		return
	}
	cfg := a.Orchestrator.DebugSpatialConfig(r.Context(), orgID, cameraID)
	zones, _ := cfg["zones"].([]map[string]interface{})
	behaviors := make([]string, 0)
	for _, z := range zones {
		if b, ok := z["behavior"].(string); ok && b != "" {
			behaviors = append(behaviors, b)
		}
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"camera_id":  cameraID.String(),
		"zone_count": len(zones),
		"behaviors":  behaviors,
		"zones":      zones,
	})
}
