package handler

import (
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/http"
	"os"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	"github.com/citevision/citevision-v2/backend/internal/alerts"
	"github.com/citevision/citevision-v2/backend/internal/audit"
	"github.com/citevision/citevision-v2/backend/internal/auth"
	"github.com/citevision/citevision-v2/backend/internal/camera"
	"github.com/citevision/citevision-v2/backend/internal/dashboard"
	"github.com/citevision/citevision-v2/backend/internal/events"
	"github.com/citevision/citevision-v2/backend/internal/evidence"
	"github.com/citevision/citevision-v2/backend/internal/ingest"
	"github.com/citevision/citevision-v2/backend/internal/identity"
	"github.com/citevision/citevision-v2/backend/internal/middleware"
	"github.com/citevision/citevision-v2/backend/internal/models"
	"github.com/citevision/citevision-v2/backend/internal/org"
	"github.com/citevision/citevision-v2/backend/internal/record"
	"github.com/citevision/citevision-v2/backend/internal/routing"
	"github.com/citevision/citevision-v2/backend/internal/rules"
	"github.com/citevision/citevision-v2/backend/internal/setup"
	"github.com/citevision/citevision-v2/backend/internal/spatial"
	"github.com/citevision/citevision-v2/backend/internal/users"
	"github.com/citevision/citevision-v2/backend/internal/ws"
)

type API struct {
	Setup       *setup.Service
	Auth        *auth.Service
	Audit       *audit.Service
	Cameras     *camera.Service
	Spatial     *spatial.Service
	Events      *events.Service
	Rules       *rules.Service
	Identity    *identity.Service
	Users       *users.Service
	Alerts      *alerts.Service
	Dashboard   *dashboard.Service
	Orgs        *org.Service
	Hub         *ws.Hub
	CatalogPath string
	SharedPath  string
	Record      *record.Service
	Evidence    *evidence.Service
	AI          *ingest.AIClient
	Routing     *routing.Service
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
		UserID: &user.ID, OrgID: a.Auth.PrimaryOrgID(r.Context(), user.ID),
		Action: "login", ResourceType: "user", ResourceID: strPtr(user.ID.String()),
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
	if claims != nil {
		orgID := middleware.GetOrgID(r.Context())
		var orgPtr *uuid.UUID
		if orgID != uuid.Nil {
			orgPtr = &orgID
		}
		_, _ = a.Audit.Append(r.Context(), audit.LogRequest{
			UserID: &claims.UserID, OrgID: orgPtr,
			Action: "logout", ResourceType: "user", ResourceID: strPtr(claims.UserID.String()),
			IPAddress: parseIP(r), UserAgent: r.UserAgent(),
		})
	}
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

func (a *API) UpdateCamera(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	id, err := uuid.Parse(chi.URLParam(r, "cameraID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
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
	if err != nil {
		writeError(w, http.StatusInternalServerError, "update failed")
		return
	}
	writeJSON(w, http.StatusOK, cam)
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

func (a *API) ProbeCamera(w http.ResponseWriter, r *http.Request) {
	var req camera.ProbeRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if err := camera.ValidateProbe(req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	result := camera.ProbeCredentials(r.Context(), req, 4*time.Second)
	writeJSON(w, http.StatusOK, result)
}

func (a *API) CameraPreview(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	id, err := uuid.Parse(chi.URLParam(r, "cameraID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	rtspURL, err := a.Cameras.BuildRTSP(r.Context(), orgID, id)
	if errors.Is(err, camera.ErrNotFound) {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "rtsp build failed")
		return
	}
	client := camera.NewGo2RTCClient()
	streamName := "cam-" + id.String()
	reg, err := client.RegisterStream(r.Context(), streamName, rtspURL)
	if err != nil {
		writeError(w, http.StatusBadGateway, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, reg)
}

func (a *API) ListRuleCatalog(w http.ResponseWriter, r *http.Request) {
	path := a.CatalogPath
	if path == "" {
		path = os.Getenv("RULE_CATALOG_PATH")
	}
	if path == "" {
		path = "../shared/rule-catalog"
	}
	templates, err := rules.LoadCatalog(path)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "catalog load failed")
		return
	}
	shared := a.SharedPath
	if shared == "" {
		shared = os.Getenv("SHARED_PATH")
	}
	if shared == "" {
		shared = "../shared"
	}
	reg, _ := rules.LoadCapabilities(shared)
	enriched := rules.EnrichCatalog(templates, reg)
	writeJSON(w, http.StatusOK, enriched)
}

func (a *API) WsAlerts(w http.ResponseWriter, r *http.Request) {
	if a.Hub == nil {
		writeError(w, http.StatusServiceUnavailable, "websocket unavailable")
		return
	}
	token := r.URL.Query().Get("token")
	if token == "" {
		token = r.Header.Get("Authorization")
		if len(token) > 7 && token[:7] == "Bearer " {
			token = token[7:]
		}
	}
	if token == "" {
		writeError(w, http.StatusUnauthorized, "token required")
		return
	}
	if _, err := a.Auth.ParseAccessToken(token); err != nil {
		writeError(w, http.StatusUnauthorized, "invalid token")
		return
	}
	a.Hub.ServeHTTP(w, r)
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
	ruleLinked := r.URL.Query().Get("rule_linked") == "true"
	includeIncomplete := r.URL.Query().Get("include_incomplete") == "true"
	list, err := a.Events.ListEnriched(r.Context(), orgID, 100, r.URL.Query().Get("event_type"), r.URL.Query().Get("camera_id"), ruleLinked, includeIncomplete)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "list failed")
		return
	}
	shared := a.SharedPath
	if shared == "" {
		shared = "../shared"
	}
	labels := loadEventLabels(shared)
	for i := range list {
		if lbl, ok := labels[list[i].EventType]; ok {
			list[i].LabelFR = lbl
		}
	}
	writeJSON(w, http.StatusOK, list)
}

func loadEventLabels(sharedDir string) map[string]string {
	path := sharedDir + "/event-labels.fr.json"
	data, err := os.ReadFile(path)
	if err != nil {
		return map[string]string{}
	}
	var labels map[string]string
	_ = json.Unmarshal(data, &labels)
	return labels
}

func (a *API) ListZones(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	list, _ := a.Spatial.ListZones(r.Context(), orgID, nil)
	cameraFilter := r.URL.Query().Get("camera_id")
	if cameraFilter != "" {
		camID, err := uuid.Parse(cameraFilter)
		if err == nil {
			filtered := make([]models.Zone, 0)
			for _, z := range list {
				if z.CameraID != nil && *z.CameraID == camID {
					filtered = append(filtered, z)
				}
			}
			list = filtered
		}
	}
	writeJSON(w, http.StatusOK, list)
}

func (a *API) DeleteZone(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	id, err := uuid.Parse(chi.URLParam(r, "zoneID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	if err := a.Spatial.DeleteZone(r.Context(), orgID, id); errors.Is(err, spatial.ErrNotFound) {
		writeError(w, http.StatusNotFound, "not found")
		return
	} else if err != nil {
		writeError(w, http.StatusInternalServerError, "delete failed")
		return
	}
	claims := middleware.GetClaims(r.Context())
	rid := id.String()
	_, _ = a.Audit.Append(r.Context(), audit.LogRequest{
		OrgID: &orgID, UserID: &claims.UserID, Action: "zone.delete",
		ResourceType: "zone", ResourceID: &rid,
		IPAddress: parseIP(r), UserAgent: r.UserAgent(),
	})
	writeJSON(w, http.StatusOK, map[string]string{"status": "deleted"})
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
	cameraFilter := r.URL.Query().Get("camera_id")
	if cameraFilter != "" {
		camID, err := uuid.Parse(cameraFilter)
		if err == nil {
			filtered := make([]models.Line, 0)
			for _, l := range list {
				if l.CameraID != nil && *l.CameraID == camID {
					filtered = append(filtered, l)
				}
			}
			list = filtered
		}
	}
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

func (a *API) DeleteLine(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	id, err := uuid.Parse(chi.URLParam(r, "lineID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	if err := a.Spatial.DeleteLine(r.Context(), orgID, id); errors.Is(err, spatial.ErrNotFound) {
		writeError(w, http.StatusNotFound, "not found")
		return
	} else if err != nil {
		writeError(w, http.StatusInternalServerError, "delete failed")
		return
	}
	claims := middleware.GetClaims(r.Context())
	rid := id.String()
	_, _ = a.Audit.Append(r.Context(), audit.LogRequest{
		OrgID: &orgID, UserID: &claims.UserID, Action: "line.delete",
		ResourceType: "line", ResourceID: &rid,
		IPAddress: parseIP(r), UserAgent: r.UserAgent(),
	})
	writeJSON(w, http.StatusOK, map[string]string{"status": "deleted"})
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
	rule, err := a.Rules.Create(r.Context(), orgID, req.SiteID, req.Name, req.Description, rules.StampUserOrigin(req.Definition), req.Priority)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	claims := middleware.GetClaims(r.Context())
	rid := rule.ID.String()
	_, _ = a.Audit.Append(r.Context(), audit.LogRequest{
		OrgID: &orgID, UserID: &claims.UserID, Action: "rule.create",
		ResourceType: "rule", ResourceID: &rid,
		IPAddress: parseIP(r), UserAgent: r.UserAgent(),
	})
	writeJSON(w, http.StatusCreated, rule)
}

func (a *API) UpdateRule(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	ruleID, err := uuid.Parse(chi.URLParam(r, "ruleID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	var req struct {
		IsEnabled   *bool           `json:"is_enabled"`
		Priority    *int            `json:"priority"`
		Name        *string         `json:"name"`
		Description *string         `json:"description"`
		Definition  json.RawMessage `json:"definition"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	def := req.Definition
	if len(def) > 0 {
		def = rules.StampUserOrigin(def)
	}
	rule, err := a.Rules.Update(r.Context(), orgID, ruleID, req.IsEnabled, req.Priority, req.Name, req.Description, def)
	if errors.Is(err, rules.ErrNotFound) {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "update failed")
		return
	}
	claims := middleware.GetClaims(r.Context())
	rid := rule.ID.String()
	action := "rule.update"
	if req.IsEnabled != nil && !*req.IsEnabled {
		action = "rule.disable"
	} else if req.IsEnabled != nil && *req.IsEnabled {
		action = "rule.enable"
	}
	_, _ = a.Audit.Append(r.Context(), audit.LogRequest{
		OrgID: &orgID, UserID: &claims.UserID, Action: action,
		ResourceType: "rule", ResourceID: &rid,
		IPAddress: parseIP(r), UserAgent: r.UserAgent(),
	})
	writeJSON(w, http.StatusOK, rule)
}

func (a *API) DeleteRule(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	ruleID, err := uuid.Parse(chi.URLParam(r, "ruleID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	if err := a.Rules.Delete(r.Context(), orgID, ruleID); errors.Is(err, rules.ErrNotFound) {
		writeError(w, http.StatusNotFound, "not found")
		return
	} else if err != nil {
		writeError(w, http.StatusInternalServerError, "delete failed")
		return
	}
	claims := middleware.GetClaims(r.Context())
	rid := ruleID.String()
	_, _ = a.Audit.Append(r.Context(), audit.LogRequest{
		OrgID: &orgID, UserID: &claims.UserID, Action: "rule.delete",
		ResourceType: "rule", ResourceID: &rid,
		IPAddress: parseIP(r), UserAgent: r.UserAgent(),
	})
	writeJSON(w, http.StatusOK, map[string]string{"status": "deleted"})
}

func (a *API) InternalListActiveRules(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	list, err := a.Rules.ListActive(r.Context(), orgID, nil)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "list failed")
		return
	}
	writeJSON(w, http.StatusOK, list)
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
	a.ListAlertsEnriched(w, r)
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
	if a.Hub != nil {
		a.Hub.Broadcast(map[string]interface{}{"type": "alert", "alert": a2})
	}
	writeJSON(w, http.StatusCreated, a2)
}

func (a *API) AcknowledgeAlert(w http.ResponseWriter, r *http.Request) {
	a.ArchiveAlert(w, r)
}

func (a *API) ArchiveAlert(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	id, err := uuid.Parse(chi.URLParam(r, "alertID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	var req struct {
		Comment          string          `json:"comment"`
		EvidenceSnapshot json.RawMessage `json:"evidence_snapshot"`
	}
	_ = json.NewDecoder(r.Body).Decode(&req)
	claims := middleware.GetClaims(r.Context())
	a2, err := a.Alerts.ArchiveAlert(r.Context(), orgID, id, alerts.ArchiveRequest{
		Comment:          req.Comment,
		EvidenceSnapshot: req.EvidenceSnapshot,
		ArchivedBy:       &claims.UserID,
	})
	if errors.Is(err, alerts.ErrNotFound) {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "archive failed")
		return
	}
	rid := id.String()
	_, _ = a.Audit.Append(r.Context(), audit.LogRequest{
		OrgID: &orgID, UserID: &claims.UserID, Action: "alert.archive",
		ResourceType: "alert", ResourceID: &rid,
		IPAddress: parseIP(r), UserAgent: r.UserAgent(),
	})
	writeJSON(w, http.StatusOK, a2)
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
	limit, offset := 100, 0
	if l := r.URL.Query().Get("limit"); l != "" {
		fmt.Sscanf(l, "%d", &limit)
	}
	if o := r.URL.Query().Get("offset"); o != "" {
		fmt.Sscanf(o, "%d", &offset)
	}
	entries, err := a.Audit.ListEnriched(r.Context(), orgID, limit, offset, r.URL.Query().Get("action"))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "list failed")
		return
	}
	writeJSON(w, http.StatusOK, entries)
}

func (a *API) VerifyAuditChain(w http.ResponseWriter, r *http.Request) {
	ok, err := a.Audit.VerifyChain(r.Context(), 500)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "verify failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"valid": ok})
}

func (a *API) DashboardSummary(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	summary, err := a.Dashboard.Summary(r.Context(), orgID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "summary failed")
		return
	}
	writeJSON(w, http.StatusOK, summary)
}

func (a *API) ListSurveillanceLists(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	listType := r.URL.Query().Get("list_type")
	list, err := a.Identity.List(r.Context(), orgID, listType)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "list failed")
		return
	}
	writeJSON(w, http.StatusOK, list)
}

func (a *API) CreateSurveillanceList(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	var req identity.CreateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if req.Name == "" || req.ListType == "" {
		writeError(w, http.StatusBadRequest, "name and list_type required")
		return
	}
	l, err := a.Identity.Create(r.Context(), orgID, req)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "create failed")
		return
	}
	writeJSON(w, http.StatusCreated, l)
}

func (a *API) DeleteSurveillanceList(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	id, err := uuid.Parse(chi.URLParam(r, "listID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	if err := a.Identity.Delete(r.Context(), orgID, id); errors.Is(err, identity.ErrNotFound) {
		writeError(w, http.StatusNotFound, "not found")
		return
	} else if err != nil {
		writeError(w, http.StatusInternalServerError, "delete failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "deleted"})
}

func (a *API) AddSurveillanceListEntry(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	listID, err := uuid.Parse(chi.URLParam(r, "listID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	var req map[string]interface{}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if req["identifier"] == nil && req["plate"] == nil {
		writeError(w, http.StatusBadRequest, "identifier required")
		return
	}
	if req["identifier"] == nil {
		req["identifier"] = req["plate"]
	}
	l, err := a.Identity.AppendEntry(r.Context(), orgID, listID, req)
	if errors.Is(err, identity.ErrNotFound) {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "append failed")
		return
	}
	writeJSON(w, http.StatusOK, l)
}

func (a *API) ListUsers(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	list, err := a.Users.List(r.Context(), orgID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "list failed")
		return
	}
	writeJSON(w, http.StatusOK, list)
}

func (a *API) CreateUser(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	var req struct {
		Email    string `json:"email"`
		FullName string `json:"full_name"`
		Password string `json:"password"`
		Role     string `json:"role"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	member, err := a.Users.Create(r.Context(), orgID, users.CreateMemberRequest{
		Email: req.Email, FullName: req.FullName, Password: req.Password,
		Role: users.FrontendRoleToBackend(req.Role),
	})
	if errors.Is(err, users.ErrAlreadyMember) {
		writeError(w, http.StatusConflict, "user already in organization")
		return
	}
	if errors.Is(err, users.ErrInvalidRole) {
		writeError(w, http.StatusBadRequest, "invalid role")
		return
	}
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, member)
}

func (a *API) UpdateUser(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	userID, err := uuid.Parse(chi.URLParam(r, "userID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid id")
		return
	}
	var req struct {
		Role     *string `json:"role"`
		IsActive *bool   `json:"is_active"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	update := users.UpdateMemberRequest{IsActive: req.IsActive}
	if req.Role != nil {
		r := users.FrontendRoleToBackend(*req.Role)
		update.Role = &r
	}
	member, err := a.Users.Update(r.Context(), orgID, userID, update)
	if errors.Is(err, users.ErrNotFound) {
		writeError(w, http.StatusNotFound, "not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "update failed")
		return
	}
	writeJSON(w, http.StatusOK, member)
}

func strPtr(s string) *string { return &s }

func parseIP(r *http.Request) net.IP {
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return net.ParseIP(r.RemoteAddr)
	}
	return net.ParseIP(host)
}
