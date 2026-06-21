package handler

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"

	"github.com/citevision/citevision-v2/backend/internal/system"
)

func (a *API) SystemStatus(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, system.GetStatus())
}

func (a *API) SystemSetStartMode(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Mode string `json:"mode"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if !system.ValidStartMode(req.Mode) {
		writeError(w, http.StatusBadRequest, "invalid mode: must be auto or manual")
		return
	}
	res, err := system.SetStartMode(req.Mode)
	if errors.Is(err, system.ErrInvalidStartMode) {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if errors.Is(err, system.ErrServiceNotRegistered) {
		writeJSON(w, http.StatusConflict, res)
		return
	}
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, res)
		return
	}
	writeJSON(w, http.StatusOK, res)
}

func (a *API) SystemServiceAction(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Action string `json:"action"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	if !system.ValidServiceAction(req.Action) {
		writeError(w, http.StatusBadRequest, "invalid action: must be start or stop")
		return
	}
	res, err := system.ServiceAction(req.Action)
	if errors.Is(err, system.ErrServiceNotRegistered) {
		writeJSON(w, http.StatusConflict, res)
		return
	}
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, res)
		return
	}
	writeJSON(w, http.StatusOK, res)
}

func (a *API) SystemUninstallStream(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	mode := q.Get("mode")
	// backward-compat: keep_data=true → soft mode if no explicit mode
	keepData := q.Get("keep_data") == "true"
	if mode != "" && !system.ValidMode(mode) {
		writeError(w, http.StatusBadRequest, "invalid mode: must be restart|soft|standard|full|nuclear")
		return
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")

	flusher, ok := w.(http.Flusher)
	if !ok {
		writeError(w, http.StatusInternalServerError, "streaming not supported")
		return
	}

	for evt := range system.UninstallStream(r.Context(), mode, keepData) {
		payload, _ := json.Marshal(evt)
		fmt.Fprintf(w, "data: %s\n\n", payload)
		flusher.Flush()
		if evt.Event == "done" || evt.Event == "error" {
			return
		}
	}
}
