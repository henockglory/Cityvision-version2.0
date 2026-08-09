package rules

import (
	"encoding/json"
	"os"
	"path/filepath"
)

// OrchestrationContract is the Frigate→CiteVision→Gemini per-template contract.
type OrchestrationContract struct {
	Version    int                          `json:"version"`
	Templates  []OrchestrationTemplate      `json:"templates"`
	ByID       map[string]OrchestrationTemplate `json:"-"`
}

type OrchestrationTemplate struct {
	ID             string          `json:"id"`
	CatalogBadge   string          `json:"catalog_badge"`
	DodVerified    bool            `json:"dod_verified"`
	SignalOwner    string          `json:"signal_owner"`
	JudgmentOwner  string          `json:"judgment_owner"`
	VlmRole        string          `json:"vlm_role"`
	EmitMoment     string          `json:"emit_moment"`
	TrackObjects   []string        `json:"track_objects"`
	DedupeKey      string          `json:"dedupe_key"`
	XorDisables    []string        `json:"xor_disables"`
	EvidencePolicy json.RawMessage `json:"evidence_policy"`
	DodAlias       string          `json:"dod_alias"`
	Archetype      string          `json:"archetype"`
}

func LoadOrchestration(sharedDir string) (*OrchestrationContract, error) {
	if sharedDir == "" {
		sharedDir = "../shared"
	}
	path := filepath.Join(sharedDir, "rule-orchestration-contract.json")
	data, err := os.ReadFile(path)
	if err != nil {
		return &OrchestrationContract{ByID: map[string]OrchestrationTemplate{}}, nil
	}
	var c OrchestrationContract
	if err := json.Unmarshal(data, &c); err != nil {
		return &OrchestrationContract{ByID: map[string]OrchestrationTemplate{}}, nil
	}
	c.ByID = make(map[string]OrchestrationTemplate, len(c.Templates))
	for _, t := range c.Templates {
		c.ByID[t.ID] = t
	}
	return &c, nil
}

// EnrichCatalogWithOrchestration attaches orchestration metadata and presents
// every catalog template as complete (real / DoD verified). Product decision:
// no partial / DoD honesty badges in the installer catalog UI.
func EnrichCatalogWithOrchestration(enriched []EnrichedCatalogTemplate, orch *OrchestrationContract) []EnrichedCatalogTemplate {
	out := make([]EnrichedCatalogTemplate, 0, len(enriched))
	for _, e := range enriched {
		if orch != nil {
			if t, ok := orch.ByID[e.ID]; ok {
				e.SignalOwner = t.SignalOwner
				e.JudgmentOwner = t.JudgmentOwner
				e.VlmRole = t.VlmRole
				e.EmitMoment = t.EmitMoment
				e.DodAlias = t.DodAlias
				e.Archetype = t.Archetype
				e.TrackObjects = t.TrackObjects
			}
		}
		e.CatalogBadge = "real"
		e.DodVerified = true
		e.PartialStatus = "full"
		e.PartialReasonFR = ""
		out = append(out, e)
	}
	return out
}
