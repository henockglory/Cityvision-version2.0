package handler

import (
	"encoding/json"
	"net/http"
	"strconv"
	"time"

	"github.com/google/uuid"

	"github.com/citevision/citevision-v2/backend/internal/middleware"
	"github.com/citevision/citevision-v2/backend/internal/routing"
)

// presetMeta describes an integration preset for the UI gallery.
type presetMeta struct {
	ID          string `json:"id"`
	Label       string `json:"label"`
	Category    string `json:"category"`
	Description string `json:"description"`
	DocsURL     string `json:"docs_url"`
}

var integrationPresets = []presetMeta{
	{ID: "n8n", Label: "n8n", Category: "automation", Description: "Self-hosted workflow automation. Use a Webhook trigger node.", DocsURL: "https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/"},
	{ID: "make", Label: "Make (Integromat)", Category: "automation", Description: "Cloud automation. Use a Custom Webhook trigger.", DocsURL: "https://www.make.com/en/help/tools/webhooks"},
	{ID: "zapier", Label: "Zapier", Category: "automation", Description: "Cloud automation. Use a Catch Hook trigger.", DocsURL: "https://zapier.com/apps/webhook/integrations"},
	{ID: "slack", Label: "Slack", Category: "chat", Description: "Posts a formatted message to a Slack Incoming Webhook.", DocsURL: "https://api.slack.com/messaging/webhooks"},
	{ID: "teams", Label: "Microsoft Teams", Category: "chat", Description: "Posts an Adaptive MessageCard to a Teams Incoming Webhook.", DocsURL: "https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/add-incoming-webhook"},
	{ID: "discord", Label: "Discord", Category: "chat", Description: "Posts an embed to a Discord channel webhook.", DocsURL: "https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks"},
}

// ListIntegrationPresets returns the catalog of supported webhook presets.
func (a *API) ListIntegrationPresets(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"presets":         integrationPresets,
		"signing_enabled": routing.SigningEnabled(),
	})
}

// TestIntegrationWebhook sends a sample alert payload to a URL/preset so the
// operator can verify connectivity before saving a routing rule.
func (a *API) TestIntegrationWebhook(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	var req struct {
		URL    string `json:"url"`
		Preset string `json:"preset"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil || req.URL == "" {
		writeError(w, http.StatusBadRequest, "url required")
		return
	}
	payload := map[string]interface{}{
		"org_id":     orgID.String(),
		"alert_id":   uuid.NewString(),
		"title":      "CiteVision test alert",
		"severity":   "medium",
		"timestamp":  time.Now().UTC().Format(time.RFC3339),
		"rule_name":  "Integration test",
		"event_type": "test",
		"camera_id":  "cam-test",
		"test":       true,
	}
	if err := routing.PostWebhookPreset(req.URL, req.Preset, payload); err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]interface{}{"ok": false, "error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"ok": true})
}

// ListDeliveryLog returns recent webhook/email delivery attempts for the org.
func (a *API) ListDeliveryLog(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	limit := 100
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			limit = n
		}
	}
	entries, err := a.Alerts.ListDeliveryLog(r.Context(), orgID, limit)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to load delivery log")
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"entries": entries})
}
