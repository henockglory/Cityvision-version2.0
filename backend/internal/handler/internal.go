package handler

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	"github.com/citevision/citevision-v2/backend/internal/alerts"
	"github.com/citevision/citevision-v2/backend/internal/notify"
	"github.com/citevision/citevision-v2/backend/internal/record"
)

func (a *API) InternalNotifyEmail(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	var req struct {
		To      string `json:"to"`
		Subject string `json:"subject"`
		Message string `json:"message"`
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
	if err := notify.SendAlert(cfg, req.To, subject, req.Message); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "sent"})
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
		RuleID string `json:"rule_id"`
		Delta  int    `json:"delta"`
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
	if err := a.Alerts.IncrementRuleCounter(r.Context(), orgID, ruleID, req.Delta); err != nil {
		writeError(w, http.StatusInternalServerError, "counter failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
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
	body, _ := json.Marshal(req.Payload)
	httpReq, err := http.NewRequestWithContext(r.Context(), http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid url")
		return
	}
	httpReq.Header.Set("Content-Type", "application/json")
	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(httpReq)
	if err != nil {
		writeError(w, http.StatusBadGateway, err.Error())
		return
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, resp.Body)
	writeJSON(w, http.StatusOK, map[string]interface{}{"status": "sent", "http_status": resp.StatusCode})
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
