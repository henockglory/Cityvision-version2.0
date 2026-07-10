package handler

import (
	"context"
	"net/http"
	"time"

	"github.com/google/uuid"
)

func (a *API) triggerFrigateSync(ctx context.Context, orgID uuid.UUID, cameraID *uuid.UUID) {
	if a.Frigate == nil || !a.Frigate.Enabled() {
		return
	}
	if cameraID != nil {
		a.Frigate.SyncCamera(ctx, orgID, *cameraID)
		return
	}
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
		defer cancel()
		_ = a.Frigate.RebuildAll(ctx)
	}()
}

func (a *API) FrigateHealth(w http.ResponseWriter, r *http.Request) {
	if a.Frigate == nil {
		writeJSON(w, http.StatusOK, map[string]interface{}{"enabled": false})
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()
	writeJSON(w, http.StatusOK, a.Frigate.Status(ctx))
}

func (a *API) InternalFrigateRebuild(w http.ResponseWriter, r *http.Request) {
	if a.Frigate == nil || !a.Frigate.Enabled() {
		writeJSON(w, http.StatusOK, map[string]string{"status": "disabled"})
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Minute)
	defer cancel()
	if err := a.Frigate.RebuildAll(ctx); err != nil {
		writeError(w, http.StatusBadGateway, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}
