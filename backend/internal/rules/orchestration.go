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

// EnrichCatalogWithOrchestration attaches orchestration fields and enforces
// catalog honesty: never advertise operational "full" when badge is partial
// and DoD is not verified.
func EnrichCatalogWithOrchestration(enriched []EnrichedCatalogTemplate, orch *OrchestrationContract) []EnrichedCatalogTemplate {
	if orch == nil || len(orch.ByID) == 0 {
		return enriched
	}
	out := make([]EnrichedCatalogTemplate, 0, len(enriched))
	for _, e := range enriched {
		t, ok := orch.ByID[e.ID]
		if !ok {
			out = append(out, e)
			continue
		}
		e.SignalOwner = t.SignalOwner
		e.JudgmentOwner = t.JudgmentOwner
		e.VlmRole = t.VlmRole
		e.EmitMoment = t.EmitMoment
		e.DodAlias = t.DodAlias
		e.Archetype = t.Archetype
		e.CatalogBadge = t.CatalogBadge
		e.DodVerified = t.DodVerified
		e.TrackObjects = t.TrackObjects
		// A.4 honesty: without DoD, do not present as fully operational.
		if !t.DodVerified && t.CatalogBadge == "partial" {
			if e.PartialStatus == "" || e.PartialStatus == "full" {
				e.PartialStatus = "requires_external"
			}
			if e.PartialReasonFR == "" {
				e.PartialReasonFR = "Orchestration Frigate/CiteVision/Gemini déclarée — badge real uniquement après validate_rule + galerie (dod_alias=" + t.DodAlias + ")."
			}
		}
		if t.DodVerified {
			e.PartialStatus = "full"
			e.PartialReasonFR = ""
		}
		out = append(out, e)
	}
	return out
}
