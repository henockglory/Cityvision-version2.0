package handler

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"time"

	"github.com/google/uuid"

	"github.com/citevision/citevision-v2/backend/internal/alerts"
	"github.com/citevision/citevision-v2/backend/internal/auth"
	"github.com/citevision/citevision-v2/backend/internal/middleware"
	"github.com/citevision/citevision-v2/backend/internal/notify"
	"github.com/citevision/citevision-v2/backend/internal/org"
)

func (a *API) UpdateMe(w http.ResponseWriter, r *http.Request) {
	claims := middleware.GetClaims(r.Context())
	var req struct {
		FullName *string `json:"full_name"`
		Email    *string `json:"email"`
		Password *string `json:"password"`
		Locale   *string `json:"locale"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	u, err := a.Auth.UpdateProfile(r.Context(), claims.UserID, auth.UpdateProfileRequest{
		FullName: req.FullName,
		Email:    req.Email,
		Password: req.Password,
		Locale:   req.Locale,
	})
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"user": u})
}

func (a *API) GetOrganization(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	o, err := a.Orgs.Get(r.Context(), orgID)
	if errors.Is(err, org.ErrNotFound) {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "lookup failed")
		return
	}
	writeJSON(w, http.StatusOK, o)
}

func (a *API) UpdateOrganization(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	var req org.UpdateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	o, err := a.Orgs.Update(r.Context(), orgID, req)
	if errors.Is(err, org.ErrNotFound) {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "update failed")
		return
	}
	writeJSON(w, http.StatusOK, o)
}

func (a *API) TestSMTP(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	var req struct {
		To string `json:"to"`
	}
	_ = json.NewDecoder(r.Body).Decode(&req)
	if req.To == "" {
		writeError(w, http.StatusBadRequest, "to required")
		return
	}
	o, err := a.Orgs.Get(r.Context(), orgID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "org lookup failed")
		return
	}
	cfg := notify.ParseSMTP(o.SMTPConfig)
	if err := notify.SendTest(cfg, req.To); err != nil {
		writeError(w, http.StatusBadGateway, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "sent"})
}

func (a *API) ResetDemo(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	rules, _ := a.Rules.List(r.Context(), orgID)
	for _, rule := range rules {
		if rule.Description != nil && len(*rule.Description) > 8 && (*rule.Description)[:8] == "Activée:" {
			_ = a.Rules.Delete(r.Context(), orgID, rule.ID)
		}
	}
	lists, _ := a.Identity.List(r.Context(), orgID, "")
	for _, list := range lists {
		_ = a.Identity.Delete(r.Context(), orgID, list.ID)
	}
	_, _ = a.Alerts.PurgeForOrg(r.Context(), orgID)
	writeJSON(w, http.StatusOK, map[string]string{"status": "demo_reset"})
}

func (a *API) PurgeAlertsDemo(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	n, err := a.Alerts.PurgeForOrg(r.Context(), orgID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "purge failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"status": "purged", "deleted": n})
}

// PurgeOrgCommercial disables all rules and purges alerts, events, and evidence media for the org.
func (a *API) PurgeOrgCommercial(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	ctx := r.Context()

	rulesDisabled, err := a.Rules.DisableAll(ctx, orgID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "disable rules failed")
		return
	}
	rulesPurged, err := a.Rules.PurgeNonUserRules(ctx, orgID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "purge non-user rules failed")
		return
	}
	alertsDeleted, err := a.Alerts.PurgeForOrg(ctx, orgID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "purge alerts failed")
		return
	}
	eventsDeleted, err := a.Events.PurgeForOrg(ctx, orgID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "purge events failed")
		return
	}
	evidenceObjects := 0
	if a.Evidence != nil && a.Evidence.Available() {
		evidenceObjects, err = a.Evidence.PurgeOrg(ctx, orgID)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "purge evidence failed")
			return
		}
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"status":                   "purged",
		"rules_disabled":           rulesDisabled,
		"rules_purged":            rulesPurged,
		"alerts_deleted":           alertsDeleted,
		"events_deleted":           eventsDeleted,
		"evidence_objects_deleted": evidenceObjects,
	})
}

func parseAlertListFilter(r *http.Request) alerts.ListFilter {
	f := alerts.ListFilter{Limit: 100}
	q := r.URL.Query()
	f.Status = q.Get("status")
	f.Severity = q.Get("severity")
	f.CameraID = q.Get("camera_id")
	if rid := q.Get("rule_id"); rid != "" {
		if id, err := uuid.Parse(rid); err == nil {
			f.RuleID = &id
		}
	}
	if lim := q.Get("limit"); lim != "" {
		if n, err := strconv.Atoi(lim); err == nil && n > 0 {
			f.Limit = n
		}
	}
	if off := q.Get("offset"); off != "" {
		if n, err := strconv.Atoi(off); err == nil && n >= 0 {
			f.Offset = n
		}
	}
	if from := q.Get("from"); from != "" {
		if t, err := time.Parse(time.RFC3339, from); err == nil {
			f.From = &t
		}
	}
	if to := q.Get("to"); to != "" {
		if t, err := time.Parse(time.RFC3339, to); err == nil {
			f.To = &t
		}
	}
	f.IncludeIncomplete = q.Get("include_incomplete") == "true"
	return f
}

func (a *API) ListAlertsEnriched(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	list, err := a.Alerts.ListEnriched(r.Context(), orgID, parseAlertListFilter(r))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "list failed")
		return
	}
	writeJSON(w, http.StatusOK, list)
}

func (a *API) StartTOTP(w http.ResponseWriter, r *http.Request) {
	claims := middleware.GetClaims(r.Context())
	secret, uri, err := a.Auth.EnableTOTP(r.Context(), claims.UserID)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"secret": secret, "uri": uri})
}

func (a *API) ConfirmTOTPSetup(w http.ResponseWriter, r *http.Request) {
	claims := middleware.GetClaims(r.Context())
	var req struct {
		Code string `json:"code"`
	}
	_ = json.NewDecoder(r.Body).Decode(&req)
	if err := a.Auth.ConfirmTOTP(r.Context(), claims.UserID, req.Code); err != nil {
		writeError(w, http.StatusBadRequest, "invalid code")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "enabled"})
}

// unused import guard removed
