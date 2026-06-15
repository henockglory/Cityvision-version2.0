package handler

import (
	"encoding/json"
	"net/http"
	"net/url"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	"github.com/citevision/citevision-v2/backend/internal/evidence"
)

func (a *API) InternalEvidenceUpload(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	if a.Evidence == nil || !a.Evidence.Available() {
		writeError(w, http.StatusServiceUnavailable, "evidence storage unavailable")
		return
	}
	if err := r.ParseMultipartForm(32 << 20); err != nil {
		writeError(w, http.StatusBadRequest, "invalid multipart form")
		return
	}
	cameraID := r.FormValue("camera_id")
	eventID := r.FormValue("event_id")
	meta := map[string]interface{}{}
	if metaJSON := r.FormValue("metadata"); metaJSON != "" {
		_ = json.Unmarshal([]byte(metaJSON), &meta)
	}

	in := evidence.UploadInput{
		OrgID: orgID, CameraID: cameraID, EventID: eventID, Metadata: meta,
	}
	if f, hdr, err := r.FormFile("clip"); err == nil {
		defer f.Close()
		in.Clip = f
		in.ClipSize = hdr.Size
	}
	if f, hdr, err := r.FormFile("scene"); err == nil {
		defer f.Close()
		in.Scene = f
		in.SceneSize = hdr.Size
	}
	if f, hdr, err := r.FormFile("subject"); err == nil {
		defer f.Close()
		in.Subject = f
		in.SubjectSz = hdr.Size
	}

	pkg, err := a.Evidence.UploadPackage(r.Context(), in)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"package":  pkg,
		"evidence": map[string]interface{}{"package": pkg},
	})
}

func (a *API) ServeEvidenceAsset(w http.ResponseWriter, r *http.Request) {
	_, err := uuid.Parse(chi.URLParam(r, "orgID"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid org id")
		return
	}
	if a.Evidence == nil || !a.Evidence.Available() {
		writeError(w, http.StatusServiceUnavailable, "evidence storage unavailable")
		return
	}
	key := r.URL.Query().Get("key")
	if key == "" {
		writeError(w, http.StatusBadRequest, "key required")
		return
	}
	decoded, err := url.QueryUnescape(key)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid key")
		return
	}
	if !strings.HasPrefix(decoded, "orgs/") {
		writeError(w, http.StatusForbidden, "invalid asset key")
		return
	}
	presigned, err := a.Evidence.PresignedGet(r.Context(), decoded)
	if err != nil {
		writeError(w, http.StatusNotFound, "asset not found")
		return
	}
	http.Redirect(w, r, presigned, http.StatusTemporaryRedirect)
}
