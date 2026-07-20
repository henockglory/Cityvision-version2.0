package handler

import (
	"net/http"

	"github.com/citevision/citevision-v2/backend/internal/aimodels"
	"github.com/citevision/citevision-v2/backend/internal/middleware"
)

// GetModelPack serves the extensible AI model registry merged with live /health [Phase D].
func (a *API) GetModelPack(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	pack, err := aimodels.BuildPack(r.Context(), a.AI, a.sharedRoot(), orgID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, pack)
}
