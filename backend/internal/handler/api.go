package handler

import (
	"encoding/json"
	"errors"
	"net"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	"github.com/citevision/citevision-v2/backend/internal/alerts"
	"github.com/citevision/citevision-v2/backend/internal/audit"
	"github.com/citevision/citevision-v2/backend/internal/auth"
	"github.com/citevision/citevision-v2/backend/internal/camera"
	"github.com/citevision/citevision-v2/backend/internal/events"
	"github.com/citevision/citevision-v2/backend/internal/middleware"
	"github.com/citevision/citevision-v2/backend/internal/models"
	"github.com/citevision/citevision-v2/backend/internal/rules"
	"github.com/citevision/citevision-v2/backend/internal/setup"
	"github.com/citevision/citevision-v2/backend/internal/spatial"
)

type API struct {
	Setup *setup.Service
	Auth  *auth.Service
	Audit *audit.Service
	Cameras *camera.Service
	Spatial *spatial.Service
	Events  *events.Service
	Rules   *rules.Service
	Alerts  *alerts.Service
}

func writeJSON(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

func (a *API) SetupStatus(w http.ResponseWriter, r *http.Request) {
	status, err := a.Setup.Status(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "status check failed")
		return
	}
	writeJSON(w, http.StatusOK, status)
}

func (a *API) SetupComplete(w http.ResponseWriter, r *http.Request) {
	var req models.SetupCompleteRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	resp, err := a.Setup.Complete(r.Context(), req)
	if errors.Is(err, setup.ErrAlreadyInitialized) {
		writeError(w, http.StatusConflict, "system already initialized")
		return
	}
	if errors.Is(err, setup.ErrInvalidSetup) {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "setup failed")
		return
	}
	_, _ = a.Audit.Append(r.Context(), audit.LogRequest{
		Action: "setup.complete", ResourceType: "system",
		ResourceID: strPtr(resp.OrgID.String()),
		IPAddress: parseIP(r), UserAgent: r.UserAgent(),
		Payload: map[string]interface{}{"org_id": resp.OrgID, "user_id": resp.UserID},
	})
	writeJSON(w, http.StatusCreated, resp)
}

func (a *API) Login(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Email    string `json:"email"`
		Password string `json:"password"`
		TOTPCode string `json:"totp_code"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	pair, user, err := a.Auth.Login(r.Context(), req.Email, req.Password, req.TOTPCode)
	if errors.Is(err, auth.ErrTOTPRequired) {
		writeJSON(w, http.StatusUnauthorized, map[string]interface{}{"error": "totp_required", "totp_required": true})
		return
	}
	if err != nil {
		writeError(w, http.StatusUnauthorized, "invalid credentials")
		return
	}
	_, _ = a.Audit.Append(r.Context(), audit.LogRequest{
		UserID: &user.ID, Action: "login", ResourceType: "user", ResourceID: strPtr(user.ID.String()),
		IPAddress: parseIP(r), UserAgent: r.UserAgent(),
	})
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"access_token":  pair.AccessToken,
		"refresh_token": pair.RefreshToken,
		"session_id":    pair.SessionID,
		"expires_in":    pair.ExpiresIn,
		"user":          user,
	})
}

func (a *API) Me(w http.ResponseWriter, r *http.Request) {
	claims := middleware.GetClaims(r.Context())
	u, err := a.Auth.GetUserByID(r.Context(), claims.UserID)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"user":   u,
		"role":   claims.Role,
		"org_id": claims.OrgID,
	})
}

func (a *API) Refresh(w http.ResponseWriter, r *http.Request) {
	var req struct {
		RefreshToken string `json:"refresh_token"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	pair, err := a.Auth.Refresh(r.Context(), req.RefreshToken)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "invalid refresh token")
		return
	}
	writeJSON(w, http.StatusOK, pair)
}

func (a *API) Logout(w http.ResponseWriter, r *http.Request) {
	var req struct {
		RefreshToken string `json:"refresh_token"`
		SessionID    string `json:"session_id"`
	}
	_ = json.NewDecoder(r.Body).Decode(&req)
	claims := middleware.GetClaims(r.Context())
	sessionID := req.SessionID
	if sessionID == "" && claims != nil {
		sessionID = claims.SessionID
	}
	_ = a.Auth.Logout(r.Context(), req.RefreshToken, sessionID)
	w.WriteHeader(http.StatusNoContent)
}

func (a *API) ListCameras(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	var siteID *uuid.UUID
	if s := r.URL.Query().Get("site_id"); s != "" {
		id, err := uuid.Parse(s)
		if err == nil {
			siteID = &id
		}
	}
	list, err := a.Cameras.List(r.Context(), orgID, siteID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "list failed")
		return
	}
	writeJSON(w, http.StatusOK, list)
}

func (a *API) CreateCamera(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	var req camera.CreateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	req.OrgID = orgID
	if err := camera.ValidateCreate(req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	cam, err := a.Cameras.Create(r.Context(), req)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "create failed")
		return
	}
	writeJSON(w, http.StatusCreated, cam)
}

func (a *API) GetCamera(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	id, err := uuid.Parse(chi.URLParam(r, "cameraID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	cam, err := a.Cameras.Get(r.Context(), orgID, id)
	if errors.Is(err, camera.ErrNotFound) {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	writeJSON(w, http.StatusOK, cam)
}

func (a *API) DiscoverCameras(w http.ResponseWriter, r *http.Request) {
	cidr := r.URL.Query().Get("cidr")
	if cidr == "" {
		writeError(w, http.StatusBadRequest, "cidr query param required")
		return
	}
	devices, err := camera.ScanSubnet(r.Context(), cidr, 2*time.Second)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, devices)
}

func (a *API) BuildRTSP(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	id, _ := uuid.Parse(chi.URLParam(r, "cameraID"))
	url, err := a.Cameras.BuildRTSP(r.Context(), orgID, id)
	if errors.Is(err, camera.ErrNotFound) {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"rtsp_url": camera.MaskRTSP(url)})
}

func (a *API) TestCameraStream(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	id, _ := uuid.Parse(chi.URLParam(r, "cameraID"))
	result := a.Cameras.TestStream(r.Context(), orgID, id, 5*time.Second)
	writeJSON(w, http.StatusOK, result)
}

func (a *API) IngestEvent(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	var req events.IngestRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	req.OrgID = orgID
	e, err := a.Events.Ingest(r.Context(), req)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "ingest failed")
		return
	}
	writeJSON(w, http.StatusCreated, e)
}

func (a *API) ListEvents(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	list, err := a.Events.List(r.Context(), orgID, 50)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "list failed")
		return
	}
	writeJSON(w, http.StatusOK, list)
}

func (a *API) ListZones(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	list, _ := a.Spatial.ListZones(r.Context(), orgID, nil)
	writeJSON(w, http.StatusOK, list)
}

func (a *API) CreateZone(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	var req spatial.ZoneRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	req.OrgID = orgID
	z, err := a.Spatial.CreateZone(r.Context(), req)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "create failed")
		return
	}
	writeJSON(w, http.StatusCreated, z)
}

func (a *API) ListLines(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	list, _ := a.Spatial.ListLines(r.Context(), orgID, nil)
	writeJSON(w, http.StatusOK, list)
}

func (a *API) CreateLine(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	var req spatial.LineRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	req.OrgID = orgID
	l, err := a.Spatial.CreateLine(r.Context(), req)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "create failed")
		return
	}
	writeJSON(w, http.StatusCreated, l)
}

func (a *API) ListRules(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	list, _ := a.Rules.List(r.Context(), orgID)
	writeJSON(w, http.StatusOK, list)
}

func (a *API) ListActiveRules(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	var siteID *uuid.UUID
	if s := r.URL.Query().Get("site_id"); s != "" {
		id, err := uuid.Parse(s)
		if err == nil {
			siteID = &id
		}
	}
	list, err := a.Rules.ListActive(r.Context(), orgID, siteID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "list failed")
		return
	}
	writeJSON(w, http.StatusOK, list)
}

func (a *API) CreateRule(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	var req struct {
		Name        string          `json:"name"`
		Description string          `json:"description"`
		SiteID      *uuid.UUID      `json:"site_id"`
		Definition  json.RawMessage `json:"definition"`
		Priority    int             `json:"priority"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	rule, err := a.Rules.Create(r.Context(), orgID, req.SiteID, req.Name, req.Description, req.Definition, req.Priority)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, rule)
}

func (a *API) ValidateRule(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Definition json.RawMessage `json:"definition"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if err := rules.ValidateDefinition(req.Definition); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"valid": "false", "error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"valid": true})
}

func (a *API) EvaluateRule(w http.ResponseWriter, r *http.Request) {
	var req rules.EvaluateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if len(req.Definition) == 0 {
		orgID := middleware.GetOrgID(r.Context())
		ruleID, err := uuid.Parse(chi.URLParam(r, "ruleID"))
		if err != nil {
			writeError(w, http.StatusBadRequest, "rule id or definition required")
			return
		}
		rule, err := a.Rules.Get(r.Context(), orgID, ruleID)
		if errors.Is(err, rules.ErrNotFound) {
			writeError(w, http.StatusNotFound, "rule not found")
			return
		}
		if err != nil {
			writeError(w, http.StatusInternalServerError, "lookup failed")
			return
		}
		req.Definition = rule.Definition
	}
	resp, err := rules.EvaluateDefinition(req.Definition, req.EventPayload, time.Now())
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (a *API) ListAlerts(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	list, _ := a.Alerts.ListAlerts(r.Context(), orgID, r.URL.Query().Get("status"))
	writeJSON(w, http.StatusOK, list)
}

func (a *API) CreateAlert(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	var req alerts.CreateAlertRequest
	_ = json.NewDecoder(r.Body).Decode(&req)
	req.OrgID = orgID
	a2, err := a.Alerts.CreateAlert(r.Context(), req)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "create failed")
		return
	}
	writeJSON(w, http.StatusCreated, a2)
}

func (a *API) ListIncidents(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	list, _ := a.Alerts.ListIncidents(r.Context(), orgID)
	writeJSON(w, http.StatusOK, list)
}

func (a *API) CreateIncident(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	var req alerts.CreateIncidentRequest
	_ = json.NewDecoder(r.Body).Decode(&req)
	req.OrgID = orgID
	inc, err := a.Alerts.CreateIncident(r.Context(), req)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "create failed")
		return
	}
	writeJSON(w, http.StatusCreated, inc)
}

func (a *API) ListAuditLog(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	entries, err := a.Audit.List(r.Context(), orgID, 50, 0)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "list failed")
		return
	}
	writeJSON(w, http.StatusOK, entries)
}

func strPtr(s string) *string { return &s }

func parseIP(r *http.Request) net.IP {
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return net.ParseIP(r.RemoteAddr)
	}
	return net.ParseIP(host)
}
