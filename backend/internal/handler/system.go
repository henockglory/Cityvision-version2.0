package handler

import (
	"encoding/json"
	"fmt"
	"net/http"

	"github.com/citevision/citevision-v2/backend/internal/system"
)

func (a *API) SystemStatus(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, system.GetStatus())
}

func (a *API) SystemUninstallStream(w http.ResponseWriter, r *http.Request) {
	keepData := r.URL.Query().Get("keep_data") == "true"

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")

	flusher, ok := w.(http.Flusher)
	if !ok {
		writeError(w, http.StatusInternalServerError, "streaming not supported")
		return
	}

	for evt := range system.UninstallStream(r.Context(), keepData) {
		payload, _ := json.Marshal(evt)
		fmt.Fprintf(w, "data: %s\n\n", payload)
		flusher.Flush()
		if evt.Event == "done" || evt.Event == "error" {
			return
		}
	}
}
