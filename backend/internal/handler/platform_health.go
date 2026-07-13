package handler

import (
	"net/http"
	"os"

	"github.com/citevision/citevision-v2/backend/internal/health"
	"github.com/citevision/citevision-v2/backend/internal/supervisor"
)

// InternalSupervisorRepair triggers platform repair playbooks (internal key required).
func (a *API) InternalSupervisorRepair(w http.ResponseWriter, r *http.Request) {
	if a.Orchestrator == nil {
		writeError(w, http.StatusServiceUnavailable, "orchestrator unavailable")
		return
	}
	runner := supervisor.NewRunner(supervisor.Deps{
		HealthDeps:   a.platformHealthDeps(),
		Orchestrator: a.Orchestrator,
		BackendURL:   backendURLFromEnv(),
		InternalKey:  supervisor.InternalKeyFromEnv(),
	})
	issues := []string{}
	if body := r.URL.Query().Get("issue"); body != "" {
		issues = append(issues, body)
	}
	if err := runner.Repair(r.Context(), issues); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"status": "repair_triggered", "issues": issues})
}

// PlatformHealth serves unified platform health (public, for preflight and UI).
func (a *API) PlatformHealth(w http.ResponseWriter, r *http.Request) {
	health.PlatformHandler(a.platformHealthDeps())(w, r)
}

func (a *API) platformHealthDeps() health.PlatformDeps {
	return health.PlatformDeps{
		Checker: a.HealthChecker,
		AI:      a.AI,
		Frigate: a.Frigate,
		Demo:    a.Demo,
	}
}

func backendURLFromEnv() string {
	if u := os.Getenv("BACKEND_PUBLIC_URL"); u != "" {
		return u
	}
	return "http://127.0.0.1:8081"
}
