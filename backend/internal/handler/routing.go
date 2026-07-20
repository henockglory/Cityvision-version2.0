package handler

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	"github.com/citevision/citevision-v2/backend/internal/routing"
)

func (a *API) ListRoutingRules(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	list, err := a.Routing.List(r.Context(), orgID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "list failed")
		return
	}
	writeJSON(w, http.StatusOK, list)
}

func (a *API) CreateRoutingRule(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	var req struct {
		Name     string          `json:"name"`
		Priority int             `json:"priority"`
		Match    json.RawMessage `json:"match"`
		Channels json.RawMessage `json:"channels"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil || req.Name == "" {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	rule, err := a.Routing.Create(r.Context(), orgID, req.Name, req.Priority, req.Match, req.Channels)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "create failed")
		return
	}
	writeJSON(w, http.StatusCreated, rule)
}

func (a *API) UpdateRoutingRule(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	id, err := uuid.Parse(chi.URLParam(r, "ruleID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	var req struct {
		Name     *string         `json:"name"`
		Enabled  *bool           `json:"enabled"`
		Priority *int            `json:"priority"`
		Match    json.RawMessage `json:"match"`
		Channels json.RawMessage `json:"channels"`
	}
	_ = json.NewDecoder(r.Body).Decode(&req)
	rule, err := a.Routing.Update(r.Context(), orgID, id, req.Name, req.Enabled, req.Priority, req.Match, req.Channels)
	if errors.Is(err, routing.ErrNotFound) {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "update failed")
		return
	}
	writeJSON(w, http.StatusOK, rule)
}

func (a *API) DeleteRoutingRule(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	id, err := uuid.Parse(chi.URLParam(r, "ruleID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	if err := a.Routing.Delete(r.Context(), orgID, id); errors.Is(err, routing.ErrNotFound) {
		writeError(w, http.StatusNotFound, "not found")
		return
	} else if err != nil {
		writeError(w, http.StatusInternalServerError, "delete failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "deleted"})
}

func (a *API) TestRoutingRules(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	var req struct {
		PlateNumber string `json:"plate_number"`
		FaceLabel   string `json:"face_label"`
		EventType   string `json:"event_type"`
		Severity    string `json:"severity"`
	}
	_ = json.NewDecoder(r.Body).Decode(&req)
	rules, err := a.Routing.List(r.Context(), orgID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "list failed")
		return
	}
	fields := map[string]string{
		"plate_number": strings.TrimSpace(req.PlateNumber),
		"face_label":   strings.TrimSpace(req.FaceLabel),
		"event_type":   strings.TrimSpace(req.EventType),
		"severity":     strings.ToLower(strings.TrimSpace(req.Severity)),
	}
	var matched []routing.Rule
	for _, rule := range rules {
		if rule.Enabled && routing.MatchRule(rule, fields) {
			matched = append(matched, rule)
		}
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"matched": matched, "count": len(matched)})
}
