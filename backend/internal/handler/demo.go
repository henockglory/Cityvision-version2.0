package handler

import (
	"encoding/json"
	"errors"
	"net/http"
	"path/filepath"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	"github.com/citevision/citevision-v2/backend/internal/demo"
	"github.com/citevision/citevision-v2/backend/internal/middleware"
)

func (a *API) GetDemoSettings(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	if a.Demo == nil {
		writeError(w, http.StatusServiceUnavailable, "demo service unavailable")
		return
	}
	st, err := a.Demo.GetSettings(r.Context(), orgID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to load demo settings")
		return
	}
	writeJSON(w, http.StatusOK, st)
}

func (a *API) PatchDemoSettings(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	if a.Demo == nil {
		writeError(w, http.StatusServiceUnavailable, "demo service unavailable")
		return
	}
	var req demo.PatchSettingsRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid json")
		return
	}
	st, err := a.Demo.PatchSettings(r.Context(), orgID, req)
	if err != nil {
		if errors.Is(err, demo.ErrVideoNotFound) {
			writeError(w, http.StatusNotFound, err.Error())
			return
		}
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, st)
}

func (a *API) UploadDemoVideo(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	if a.Demo == nil {
		writeError(w, http.StatusServiceUnavailable, "demo service unavailable")
		return
	}
	if err := r.ParseMultipartForm(2 << 30); err != nil {
		writeError(w, http.StatusBadRequest, "invalid multipart form")
		return
	}
	file, hdr, err := r.FormFile("video")
	if err != nil {
		writeError(w, http.StatusBadRequest, "video file required")
		return
	}
	defer file.Close()

	name := strings.TrimSpace(r.FormValue("name"))
	if name == "" && hdr.Filename != "" {
		// filepath.Base strips Windows full paths (e.g. C:\Users\...\benedicte.mp4 → benedicte.mp4).
		// We also replace any stray backslashes that slip through on some clients.
		baseName := filepath.Base(strings.ReplaceAll(hdr.Filename, "\\", "/"))
		name = strings.TrimSuffix(baseName, filepath.Ext(baseName))
		name = strings.TrimSpace(name)
	}
	contentType := hdr.Header.Get("Content-Type")
	// If the browser/curl didn't set a proper content-type, detect from filename.
	if contentType == "" || contentType == "application/octet-stream" {
		if strings.HasSuffix(strings.ToLower(hdr.Filename), ".mp4") {
			contentType = "video/mp4"
		} else {
			contentType = "video/mp4" // default — service validates extension anyway
		}
	}

	v, err := a.Demo.UploadVideo(r.Context(), orgID, name, file, hdr.Size, contentType)
	if err != nil {
		switch {
		case errors.Is(err, demo.ErrVideoLimit):
			writeError(w, http.StatusConflict, err.Error())
		case errors.Is(err, demo.ErrInvalidVideo):
			writeError(w, http.StatusBadRequest, err.Error())
		default:
			writeError(w, http.StatusInternalServerError, err.Error())
		}
		return
	}
	writeJSON(w, http.StatusAccepted, v)
}

func (a *API) GetDemoVideoStatus(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	videoID, err := uuid.Parse(chi.URLParam(r, "videoID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid video id")
		return
	}
	if a.Demo == nil {
		writeError(w, http.StatusServiceUnavailable, "demo service unavailable")
		return
	}
	v, err := a.Demo.GetVideo(r.Context(), orgID, videoID)
	if err != nil {
		if errors.Is(err, demo.ErrVideoNotFound) {
			writeError(w, http.StatusNotFound, err.Error())
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, v)
}

func (a *API) DeleteDemoVideo(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	videoID, err := uuid.Parse(chi.URLParam(r, "videoID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid video id")
		return
	}
	if a.Demo == nil {
		writeError(w, http.StatusServiceUnavailable, "demo service unavailable")
		return
	}
	if err := a.Demo.DeleteVideo(r.Context(), orgID, videoID); err != nil {
		if errors.Is(err, demo.ErrVideoNotFound) {
			writeError(w, http.StatusNotFound, err.Error())
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "deleted"})
}

func (a *API) PatchDemoVideo(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	videoID, err := uuid.Parse(chi.URLParam(r, "videoID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid video id")
		return
	}
	if a.Demo == nil {
		writeError(w, http.StatusServiceUnavailable, "demo service unavailable")
		return
	}
	var body struct {
		Name string `json:"name"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid json")
		return
	}
	v, err := a.Demo.RenameVideo(r.Context(), orgID, videoID, body.Name)
	if err != nil {
		if errors.Is(err, demo.ErrVideoNotFound) {
			writeError(w, http.StatusNotFound, err.Error())
			return
		}
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, v)
}

func (a *API) RetryDemoVideo(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	videoID, err := uuid.Parse(chi.URLParam(r, "videoID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid video id")
		return
	}
	if a.Demo == nil {
		writeError(w, http.StatusServiceUnavailable, "demo service unavailable")
		return
	}
	v, err := a.Demo.RetryVideo(r.Context(), orgID, videoID)
	if err != nil {
		if errors.Is(err, demo.ErrVideoNotFound) {
			writeError(w, http.StatusNotFound, err.Error())
			return
		}
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	writeJSON(w, http.StatusAccepted, v)
}

func (a *API) ResetDemoWorkspace(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	if a.Demo == nil {
		a.ResetDemo(w, r)
		return
	}
	result, err := a.Demo.ResetWorkspace(r.Context(), orgID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, result)
}
