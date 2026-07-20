package handler

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	"github.com/citevision/citevision-v2/backend/internal/aimodels"
	"github.com/citevision/citevision-v2/backend/internal/audit"
	"github.com/citevision/citevision-v2/backend/internal/middleware"
)

type uploadOrgModelResponse struct {
	ID                 string `json:"id"`
	SHA256             string `json:"sha256"`
	File               string `json:"file"`
	ProbeOK            bool   `json:"probe_ok"`
	HealthKey          string `json:"health_key"`
	Behavior           string `json:"behavior"`
	EventType          string `json:"event_type"`
	Template           string `json:"rule_template_id"`
	AppliesTo          string `json:"applies_to"`
	InputSource        string `json:"input_source"`
	LabelFR            string `json:"label_fr"`
	LabelEN            string `json:"label_en"`
	AIReloadOK         bool   `json:"ai_reload_ok"`
	AIReloadMessage    string `json:"ai_reload_message,omitempty"`
}

func parseOrgModelEntryFromForm(r *http.Request) (aimodels.OrgModelEntry, error) {
	entry := aimodels.OrgModelEntry{
		ID:                 strings.TrimSpace(r.FormValue("id")),
		Task:               strings.TrimSpace(r.FormValue("task")),
		Behavior:           strings.TrimSpace(r.FormValue("behavior")),
		EventType:          strings.TrimSpace(r.FormValue("event_type")),
		LabelFR:            strings.TrimSpace(r.FormValue("label_fr")),
		LabelEN:            strings.TrimSpace(r.FormValue("label_en")),
		AppliesTo:          strings.TrimSpace(r.FormValue("applies_to")),
		InputSource:        strings.TrimSpace(r.FormValue("input_source")),
		HumanDescriptionFR: strings.TrimSpace(r.FormValue("human_description_fr")),
		HumanDescriptionEN: strings.TrimSpace(r.FormValue("human_description_en")),
		Capability:         strings.TrimSpace(r.FormValue("capability")),
	}
	if raw := strings.TrimSpace(r.FormValue("input_size")); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			entry.InputSize = n
		}
	}
	if raw := strings.TrimSpace(r.FormValue("classes")); raw != "" {
		_ = json.Unmarshal([]byte(raw), &entry.Classes)
	}
	if raw := strings.TrimSpace(r.FormValue("positive_classes")); raw != "" {
		_ = json.Unmarshal([]byte(raw), &entry.PositiveClasses)
	}
	return entry, nil
}

// UploadOrgAIModel accepts multipart ONNX (file or download_url), probes it, stores under org dir [J.87].
func (a *API) UploadOrgAIModel(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	if err := r.ParseMultipartForm(256 << 20); err != nil {
		writeError(w, http.StatusBadRequest, "invalid multipart form")
		return
	}

	entry, err := parseOrgModelEntryFromForm(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	var reader io.Reader
	var closer io.Closer

	file, hdr, fileErr := r.FormFile("model")
	downloadURL := strings.TrimSpace(r.FormValue("download_url"))

	switch {
	case fileErr == nil:
		defer file.Close()
		reader = file
		if entry.ID == "" {
			base := strings.TrimSuffix(strings.ToLower(hdr.Filename), ".onnx")
			entry.ID = strings.TrimSpace(base)
		}
		if !strings.HasSuffix(strings.ToLower(hdr.Filename), ".onnx") {
			writeError(w, http.StatusBadRequest, "only .onnx files are supported")
			return
		}
	case downloadURL != "":
		body, _, dlErr := aimodels.DownloadModelFromURL(r.Context(), downloadURL)
		if dlErr != nil {
			writeError(w, http.StatusBadRequest, dlErr.Error())
			return
		}
		closer = body
		defer closer.Close()
		reader = body
	default:
		writeError(w, http.StatusBadRequest, "provide model file or download_url")
		return
	}

	saved, err := aimodels.UpsertOrgModel(orgID, entry, reader)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	aiReloadOK := false
	aiReloadMsg := ""
	if a.AI != nil {
		if reloadErr := a.AI.ReloadSecondaryModels(r.Context()); reloadErr != nil {
			aiReloadMsg = reloadErr.Error()
		} else {
			aiReloadOK = true
		}
	} else {
		aiReloadMsg = "ai client not configured"
	}

	if claims := middleware.GetClaims(r.Context()); claims != nil {
		rid := saved.ID
		a.auditLog(r.Context(), audit.LogRequest{
			OrgID: &orgID, UserID: &claims.UserID, Action: "ai_model.upload",
			ResourceType: "ai_model", ResourceID: &rid,
			IPAddress: parseIP(r), UserAgent: r.UserAgent(),
			Payload: map[string]interface{}{
				"id": saved.ID, "sha256": saved.SHA256, "probe_ok": saved.ProbeOK, "ai_reload_ok": aiReloadOK,
			},
		})
	}

	writeJSON(w, http.StatusCreated, uploadOrgModelResponse{
		ID:              saved.ID,
		SHA256:          saved.SHA256,
		File:            saved.File,
		ProbeOK:         saved.ProbeOK,
		HealthKey:       aimodels.OrgModelHealthKey(saved.ID),
		Behavior:        saved.Behavior,
		EventType:       saved.EventType,
		Template:        aimodels.CustomRuleTemplateID(saved.ID),
		AppliesTo:       saved.AppliesTo,
		InputSource:     saved.InputSource,
		LabelFR:         saved.LabelFR,
		LabelEN:         saved.LabelEN,
		AIReloadOK:      aiReloadOK,
		AIReloadMessage: aiReloadMsg,
	})
}

// ListOrgAIModels returns org-scoped ONNX models merged with live health.
func (a *API) ListOrgAIModels(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	models, err := aimodels.LoadOrgModels(orgID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	health := map[string]string{}
	if a.AI != nil {
		if h, err := a.AI.FetchHealth(r.Context()); err == nil {
			health = h
		}
	}
	type row struct {
		aimodels.OrgModelEntry
		HealthKey string `json:"health_key"`
		Loaded    bool   `json:"loaded"`
		Template  string `json:"rule_template_id"`
	}
	out := make([]row, 0, len(models))
	for _, m := range models {
		hk := aimodels.OrgModelHealthKey(m.ID)
		loaded := false
		if v, ok := health[hk]; ok {
			loaded = strings.EqualFold(v, "true") || v == "1"
		}
		out = append(out, row{
			OrgModelEntry: m,
			HealthKey:     hk,
			Loaded:        loaded,
			Template:      aimodels.CustomRuleTemplateID(m.ID),
		})
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"models": out, "health": health})
}
