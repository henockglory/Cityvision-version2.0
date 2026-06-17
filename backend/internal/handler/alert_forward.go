package handler

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	"github.com/citevision/citevision-v2/backend/internal/alerts"
	"github.com/citevision/citevision-v2/backend/internal/notify"
	"github.com/citevision/citevision-v2/backend/internal/routing"
)

func (a *API) ForwardAlert(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	alertID, err := uuid.Parse(chi.URLParam(r, "alertID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid alert id")
		return
	}
	var req struct {
		Email         string `json:"email"`
		WebhookURL    string `json:"webhook_url"`
		WebhookPreset string `json:"webhook_preset"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if req.Email == "" && req.WebhookURL == "" {
		writeError(w, http.StatusBadRequest, "email or webhook_url required")
		return
	}

	alert, err := a.Alerts.GetByID(r.Context(), orgID, alertID)
	if errors.Is(err, alerts.ErrNotFound) {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "load failed")
		return
	}

	var evSnap map[string]interface{}
	_ = json.Unmarshal(alert.EvidenceSnapshot, &evSnap)
	logEntry := map[string]interface{}{
		"timestamp": time.Now().UTC().Format(time.RFC3339),
		"channels":  []string{},
	}

	if req.Email != "" {
		o, err := a.Orgs.Get(r.Context(), orgID)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "org load failed")
			return
		}
		cfg := notify.ParseSMTP(o.SMTPConfig)
		msg := buildForwardEmailMessage(alert, evSnap)
		if err := notify.SendAlert(cfg, req.Email, "CitéVision — "+alert.Title, msg); err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		logEntry["channels"] = append(logEntry["channels"].([]string), "email")
		logEntry["email"] = req.Email
	}

	if req.WebhookURL != "" {
		payload := map[string]interface{}{
			"org_id":            orgID.String(),
			"alert_id":          alertID.String(),
			"title":             alert.Title,
			"severity":          alert.Severity,
			"timestamp":         time.Now().UTC().Format(time.RFC3339),
			"evidence_snapshot": evSnap,
			"camera_id":         alert.CameraID,
			"rule_name":         alert.RuleName,
		}
		if req.WebhookPreset != "" {
			payload["integration_preset"] = req.WebhookPreset
		}
		if err := postWebhookURL(r, req.WebhookURL, payload); err != nil {
			writeError(w, http.StatusBadGateway, err.Error())
			return
		}
		logEntry["channels"] = append(logEntry["channels"].([]string), "webhook")
		logEntry["webhook_url"] = req.WebhookURL
	}

	_ = a.Alerts.AppendForwardLog(r.Context(), orgID, alertID, logEntry)
	writeJSON(w, http.StatusOK, map[string]interface{}{"status": "sent", "log": logEntry})
}

func buildForwardEmailMessage(alert *alerts.EnrichedAlert, evSnap map[string]interface{}) string {
	var b strings.Builder
	fmt.Fprintf(&b, "Alerte : %s\n", alert.Title)
	if alert.RuleName != nil {
		fmt.Fprintf(&b, "Règle : %s\n", *alert.RuleName)
	}
	if alert.CameraID != "" {
		fmt.Fprintf(&b, "Caméra : %s\n", alert.CameraID)
	}
	b.WriteString("\nLiens vers les preuves :\n")
	appendEvidenceLinks(&b, evSnap)
	return b.String()
}

func appendEvidenceLinks(b *strings.Builder, evSnap map[string]interface{}) {
	if evSnap == nil {
		b.WriteString("(aucune preuve enregistrée)\n")
		return
	}
	pkg, _ := evSnap["package"].(map[string]interface{})
	if pkg == nil {
		b.WriteString("(aucune preuve enregistrée)\n")
		return
	}
	if clip, ok := pkg["clip"].(map[string]interface{}); ok {
		if u, ok := clip["url"].(string); ok && u != "" {
			fmt.Fprintf(b, "- Clip vidéo : %s\n", u)
		}
	}
	if imgs, ok := pkg["images"].([]interface{}); ok {
		for _, im := range imgs {
			m, _ := im.(map[string]interface{})
			if m == nil {
				continue
			}
			if u, ok := m["url"].(string); ok && u != "" {
				fmt.Fprintf(b, "- Image (%v) : %s\n", m["role"], u)
			}
		}
	}
}

func postWebhookURL(r *http.Request, url string, payload map[string]interface{}) error {
	return routing.PostWebhook(url, payload)
}

func (a *API) InternalNotificationDefaults(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	o, err := a.Orgs.Get(r.Context(), orgID)
	if err != nil {
		writeError(w, http.StatusNotFound, "org not found")
		return
	}
	var prefs map[string]interface{}
	_ = json.Unmarshal(o.NotificationPrefs, &prefs)
	out := map[string]string{}
	if v, ok := prefs["default_email_to"].(string); ok {
		out["default_email_to"] = v
	}
	if v, ok := prefs["default_webhook_url"].(string); ok {
		out["default_webhook_url"] = v
	}
	writeJSON(w, http.StatusOK, out)
}
