package handler

import (
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"strconv"
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
	if f, hdr, err := r.FormFile("plate"); err == nil {
		defer f.Close()
		in.Plate = f
		in.PlateSz = hdr.Size
	}

	pkg, err := a.Evidence.UploadPackage(r.Context(), in)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	// Back-fill the event's evidence_snapshot so the demo feed shows the event immediately.
	if eventID != "" && a.Events != nil {
		_ = a.Events.PatchEvidenceSnapshot(r.Context(), orgID, eventID, pkg)
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"package":  pkg,
		"evidence": map[string]interface{}{"package": pkg},
	})
}

func (a *API) ServeEvidenceAsset(w http.ResponseWriter, r *http.Request) {
	orgID, err := uuid.Parse(chi.URLParam(r, "orgID"))
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
	// Prevent cross-tenant access (IDOR): the object key must live under the
	// caller's org prefix. Evidence keys are "orgs/{orgID}/cameras/...".
	wantPrefix := "orgs/" + orgID.String() + "/"
	if !strings.HasPrefix(decoded, wantPrefix) {
		writeError(w, http.StatusForbidden, "invalid asset key")
		return
	}
	stat, err := a.Evidence.StatObject(r.Context(), decoded)
	if err != nil {
		writeError(w, http.StatusNotFound, "asset not found")
		return
	}
	obj, err := a.Evidence.GetObject(r.Context(), decoded)
	if err != nil {
		writeError(w, http.StatusNotFound, "asset not found")
		return
	}
	defer obj.Close()

	ct := stat.ContentType
	if ct == "" || ct == "application/octet-stream" {
		ct = contentTypeForKey(decoded)
	}
	w.Header().Set("Content-Type", ct)
	w.Header().Set("Cache-Control", "private, max-age=300")
	w.Header().Set("Content-Length", strconv.FormatInt(stat.Size, 10))
	if _, err := io.Copy(w, obj); err != nil {
		return
	}
}

func contentTypeForKey(key string) string {
	lower := strings.ToLower(key)
	switch {
	case strings.HasSuffix(lower, ".mp4"):
		return "video/mp4"
	case strings.HasSuffix(lower, ".jpg"), strings.HasSuffix(lower, ".jpeg"):
		return "image/jpeg"
	case strings.HasSuffix(lower, ".png"):
		return "image/png"
	default:
		return "application/octet-stream"
	}
}
