package handler

import (
	"encoding/json"
	"net/http"
	"os"

	"github.com/citevision/citevision-v2/backend/internal/capabilities"
	"github.com/citevision/citevision-v2/backend/internal/middleware"
	"github.com/citevision/citevision-v2/backend/internal/sceneintent"
)

func (a *API) sharedRoot() string {
	if a.SharedPath != "" {
		return a.SharedPath
	}
	if p := os.Getenv("SHARED_PATH"); p != "" {
		return p
	}
	return "../shared"
}

func (a *API) catalogRoot() string {
	if a.CatalogPath != "" {
		return a.CatalogPath
	}
	if p := os.Getenv("RULE_CATALOG_PATH"); p != "" {
		return p
	}
	return "../shared/rule-catalog"
}

// GetCapabilitiesMenu serves merged zone behaviors + health + compatible templates [K.94].
func (a *API) GetCapabilitiesMenu(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	menu, err := capabilities.BuildMenu(r.Context(), a.AI, a.sharedRoot(), a.catalogRoot(), orgID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, menu)
}

// ValidateSceneIntent checks cross-cutting zone↔règle constraints [K.96].
func (a *API) ValidateSceneIntent(w http.ResponseWriter, r *http.Request) {
	orgID := middleware.GetOrgID(r.Context())
	var req struct {
		Definition json.RawMessage `json:"definition"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid body")
		return
	}
	result := sceneintent.ValidateDefinition(r.Context(), orgID, req.Definition, a.Spatial, a.AI, a.sharedRoot())
	status := http.StatusOK
	if !result.Valid {
		status = http.StatusBadRequest
	}
	writeJSON(w, status, result)
}
