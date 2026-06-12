package handler

import (
	"encoding/json"
	"errors"
	"net"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	"github.com/citevision/citevision/backend/internal/alerts"
	"github.com/citevision/citevision/backend/internal/audit"
	"github.com/citevision/citevision/backend/internal/auth"
	"github.com/citevision/citevision/backend/internal/camera"
	"github.com/citevision/citevision/backend/internal/correlation"
	"github.com/citevision/citevision/backend/internal/dashboard"
	"github.com/citevision/citevision/backend/internal/events"
	"github.com/citevision/citevision/backend/internal/middleware"
	"github.com/citevision/citevision/backend/internal/rules"
	"github.com/citevision/citevision/backend/internal/spatial"
	"github.com/citevision/citevision/backend/internal/state"
	"github.com/citevision/citevision/backend/internal/watchlist"
)

type API struct {
	Auth        *auth.Service
	Audit       *audit.Service
	Cameras     *camera.Service
	Spatial     *spatial.Service
	Events      *events.Service
	Rules       *rules.Service
	State       *state.Service
	Correlation *correlation.Service
	Alerts      *alerts.Service
	Dashboard   *dashboard.Service
	Watchlist   *watchlist.Service
}

func writeJSON(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
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
		"expires_in":    pair.ExpiresIn,
		"user":          user,
	})
}

func (a *API) Me(w http.ResponseWriter, r *http.Request) {
	claims := middleware.GetClaims(r.Context())
	if claims == nil {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return
	}
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
	}
	_ = json.NewDecoder(r.Body).Decode(&req)
	_ = a.Auth.Logout(r.Context(), req.RefreshToken)
	w.WriteHeader(http.StatusNoContent)
}

func (a *API) SetupTOTP(w http.ResponseWriter, r *http.Request) {
	claims := middleware.GetClaims(r.Context())
	secret, uri, err := a.Auth.EnableTOTP(r.Context(), claims.UserID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "totp setup failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"secret": secret, "uri": uri})
}

func (a *API) ConfirmTOTP(w http.ResponseWriter, r *http.Request) {
	claims := middleware.GetClaims(r.Context())
	var req struct {
		Code string `json:"code"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if err := a.Auth.ConfirmTOTP(r.Context(), claims.UserID, req.Code); err != nil {
		writeError(w, http.StatusBadRequest, "invalid totp code")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "enabled"})
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

func (a *API) UpdateCamera(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	id, _ := uuid.Parse(chi.URLParam(r, "cameraID"))
	var req camera.UpdateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	cam, err := a.Cameras.Update(r.Context(), orgID, id, req)
	if errors.Is(err, camera.ErrNotFound) {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	writeJSON(w, http.StatusOK, cam)
}

func (a *API) DeleteCamera(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	id, _ := uuid.Parse(chi.URLParam(r, "cameraID"))
	if err := a.Cameras.Delete(r.Context(), orgID, id); errors.Is(err, camera.ErrNotFound) {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (a *API) DiscoverCameras(w http.ResponseWriter, r *http.Request) {
	cidr := r.URL.Query().Get("cidr")
	if cidr == "" {
		writeError(w, http.StatusBadRequest, "cidr query param required")
		return
	}
	timeout := 2 * time.Second
	devices, err := camera.ScanSubnet(r.Context(), cidr, timeout)
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

func (a *API) DashboardSummary(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	summary, err := a.Dashboard.GetSummary(r.Context(), orgID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "summary failed")
		return
	}
	writeJSON(w, http.StatusOK, summary)
}

func (a *API) ListZones(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	list, _ := a.Spatial.ListZones(r.Context(), orgID, nil)
	writeJSON(w, http.StatusOK, list)
}

func (a *API) CreateZone(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	var req spatial.ZoneRequest
	_ = json.NewDecoder(r.Body).Decode(&req)
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
	_ = json.NewDecoder(r.Body).Decode(&req)
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

func (a *API) GetState(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	entityType := chi.URLParam(r, "entityType")
	entityID := chi.URLParam(r, "entityID")
	snap, err := a.State.Get(r.Context(), orgID, entityType, entityID)
	if err != nil {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	writeJSON(w, http.StatusOK, snap)
}

func (a *API) UpsertState(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	var req struct {
		SiteID     *uuid.UUID      `json:"site_id"`
		EntityType string          `json:"entity_type"`
		EntityID   string          `json:"entity_id"`
		State      json.RawMessage `json:"state"`
	}
	_ = json.NewDecoder(r.Body).Decode(&req)
	snap, err := a.State.Upsert(r.Context(), orgID, req.SiteID, req.EntityType, req.EntityID, req.State)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "upsert failed")
		return
	}
	writeJSON(w, http.StatusOK, snap)
}

func (a *API) ListCorrelationRules(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	list, _ := a.Correlation.ListRules(r.Context(), orgID)
	writeJSON(w, http.StatusOK, list)
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

func (a *API) AddIncidentEvidence(w http.ResponseWriter, r *http.Request) {
	incidentID, _ := uuid.Parse(chi.URLParam(r, "incidentID"))
	var req alerts.EvidenceRequest
	_ = json.NewDecoder(r.Body).Decode(&req)
	ev, err := a.Alerts.AddEvidence(r.Context(), incidentID, req)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "add evidence failed")
		return
	}
	writeJSON(w, http.StatusCreated, ev)
}

func (a *API) ListWatchlist(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	list, _ := a.Watchlist.List(r.Context(), orgID, r.URL.Query().Get("type"))
	writeJSON(w, http.StatusOK, list)
}

func (a *API) CreateWatchlistEntry(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	var req watchlist.CreateRequest
	_ = json.NewDecoder(r.Body).Decode(&req)
	req.OrgID = orgID
	e, err := a.Watchlist.Create(r.Context(), req)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "create failed")
		return
	}
	writeJSON(w, http.StatusCreated, e)
}

func (a *API) MatchFace(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	id := r.URL.Query().Get("identifier")
	e, err := a.Watchlist.MatchFace(r.Context(), orgID, id)
	if errors.Is(err, watchlist.ErrNotFound) {
		writeJSON(w, http.StatusOK, map[string]bool{"matched": false})
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"matched": true, "entry": e})
}

func (a *API) MatchANPR(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	plate := r.URL.Query().Get("plate")
	e, err := a.Watchlist.MatchANPR(r.Context(), orgID, plate)
	if errors.Is(err, watchlist.ErrNotFound) {
		writeJSON(w, http.StatusOK, map[string]bool{"matched": false})
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"matched": true, "entry": e})
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
