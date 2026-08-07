package rules

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

type CapabilityMeta struct {
	LabelFR              string   `json:"label_fr"`
	RequiredConfig       []string `json:"required_config"`
	ProofFields          []string `json:"proof_fields"`
	Models               []string `json:"models"`
	UnsupportedMessageFR string   `json:"unsupported_message_fr,omitempty"`
}

type TemplateCapability struct {
	Supported            bool              `json:"supported"`
	CapabilityID         string            `json:"capability_id,omitempty"`
	HumanDescription     string            `json:"human_description,omitempty"`
	RoleSummaryFR       string            `json:"role_summary_fr,omitempty"`
	Illustration        string            `json:"illustration,omitempty"`
	DeploymentScopes    []string          `json:"deployment_scopes,omitempty"`
	Tutorial             string            `json:"tutorial,omitempty"`
	Prerequisites        []string          `json:"prerequisites,omitempty"`
	UnsupportedMessageFR string            `json:"unsupported_message_fr,omitempty"`
	ConfigSchema         json.RawMessage   `json:"configSchema,omitempty"`
}

type CapabilitiesRegistry struct {
	EventTypes map[string]CapabilityMeta    `json:"event_types"`
	Templates  map[string]TemplateCapability `json:"templates"`
}

type EnrichedCatalogTemplate struct {
	CatalogTemplate
	Supported            bool     `json:"supported"`
	CapabilityID         string   `json:"capability_id,omitempty"`
	HumanDescription     string   `json:"human_description,omitempty"`
	RoleSummaryFR        string   `json:"role_summary_fr,omitempty"`
	Illustration         string   `json:"illustration,omitempty"`
	DeploymentScopes     []string `json:"deployment_scopes,omitempty"`
	Tutorial             string   `json:"tutorial,omitempty"`
	Prerequisites        []string `json:"prerequisites,omitempty"`
	UnsupportedMessageFR string   `json:"unsupported_message_fr,omitempty"`
	// ActivationBlocked is true when partial_status requires a model/OCR/face that is not loaded.
	// Catalog tile stays visible (supported unchanged) but activation must be refused [A.4].
	ActivationBlocked      bool     `json:"activation_blocked"`
	ActivationBlockReason  string   `json:"activation_block_reason,omitempty"`
	MissingHealthKeys      []string `json:"missing_health_keys,omitempty"`
	// Orchestration contract (Frigate→CiteVision→Gemini) — see rule-orchestration-contract.json
	SignalOwner   string   `json:"signal_owner,omitempty"`
	JudgmentOwner string   `json:"judgment_owner,omitempty"`
	VlmRole       string   `json:"vlm_role,omitempty"`
	EmitMoment    string   `json:"emit_moment,omitempty"`
	DodAlias      string   `json:"dod_alias,omitempty"`
	Archetype     string   `json:"archetype,omitempty"`
	CatalogBadge  string   `json:"catalog_badge,omitempty"`
	DodVerified   bool     `json:"dod_verified,omitempty"`
	TrackObjects  []string `json:"track_objects,omitempty"`
}

func LoadCapabilities(dir string) (*CapabilitiesRegistry, error) {
	if dir == "" {
		dir = "../shared"
	}
	path := filepath.Join(dir, "ai-capabilities.json")
	data, err := os.ReadFile(path)
	if err != nil {
		return defaultRegistry(), nil
	}
	var reg CapabilitiesRegistry
	if err := json.Unmarshal(data, &reg); err != nil {
		return defaultRegistry(), nil
	}
	return &reg, nil
}

func defaultRegistry() *CapabilitiesRegistry {
	return &CapabilitiesRegistry{
		EventTypes: map[string]CapabilityMeta{},
		Templates:  map[string]TemplateCapability{},
	}
}

func ExtractPrimaryEvent(def json.RawMessage) string {
	var root map[string]interface{}
	if err := json.Unmarshal(def, &root); err != nil {
		return ""
	}
	cond, ok := root["condition"].(map[string]interface{})
	if !ok {
		return ""
	}
	return extractEventFromCondition(cond)
}

func extractEventFromCondition(node map[string]interface{}) string {
	op, _ := node["op"].(string)
	field, _ := node["field"].(string)
	if strings.EqualFold(op, "eq") && (field == "event" || field == "event_type") {
		if v, ok := node["value"].(string); ok {
			return v
		}
	}
	if children, ok := node["children"].([]interface{}); ok {
		for _, c := range children {
			if m, ok := c.(map[string]interface{}); ok {
				if ev := extractEventFromCondition(m); ev != "" {
					return ev
				}
			}
		}
	}
	return ""
}

func templateHasConfigFields(raw json.RawMessage) bool {
	if len(raw) == 0 {
		return false
	}
	var schema struct {
		Fields []json.RawMessage `json:"fields"`
	}
	if err := json.Unmarshal(raw, &schema); err != nil {
		return false
	}
	return len(schema.Fields) > 0
}

// scopesForCategory maps catalog categories to deployment scopes for filter tabs.
func scopesForCategory(category string) []string {
	switch category {
	case "crowd", "traffic", "speed", "road-enforcement", "incident":
		return []string{"national"}
	case "presence":
		return []string{"domestic"}
	case "security", "spatial", "objects", "identity", "behavior", "composite", "time", "industrial", "quality":
		return []string{"enterprise"}
	default:
		return []string{"enterprise"}
	}
}

func EnrichCatalog(templates []CatalogTemplate, reg *CapabilitiesRegistry) []EnrichedCatalogTemplate {
	return EnrichCatalogWithHealth(templates, reg, nil)
}

func healthTruthy(health map[string]string, key string) bool {
	if health == nil {
		return false
	}
	v, ok := health[key]
	if !ok {
		return false
	}
	return strings.EqualFold(v, "true") || v == "1"
}

// requiredHealthKeysForTemplate maps honest partial_status / template id to AI /health keys.
func requiredHealthKeysForTemplate(t CatalogTemplate) []string {
	switch t.PartialStatus {
	case "requires_ocr":
		// Gemini OCR under bridge also sets plate_loaded=true in /health.
		return []string{"plate_loaded"}
	case "requires_face_ai":
		return []string{"face_loaded"}
	case "requires_model":
		switch t.ID {
		case "tpl-phone-driving", "tpl-seatbelt":
			// Prefer bridge+Gemini; fall back to cabin ONNX keys only when bridge off.
			// EnrichCatalogWithHealth uses live health — accept either path via
			// requiredHealthKeysForTemplateResolved.
			return []string{"cabin_or_gemini_bridge"}
		default:
			// Unknown secondary model — block until any secondary is present is too harsh;
			// require YOLO at minimum so activation is not claimed "ready" with zero AI.
			return []string{"yolo_loaded"}
		}
	default:
		return nil
	}
}

// healthSatisfies reports whether a required key is met, including Gemini bridge aliases.
func healthSatisfies(health map[string]string, key string) bool {
	if healthTruthy(health, key) {
		return true
	}
	if key == "cabin_or_gemini_bridge" {
		bridge := healthTruthy(health, "frigate_vlm_bridge")
		gemini := healthTruthy(health, "gemini_configured") || healthTruthy(health, "gemini_enabled")
		if bridge && gemini {
			return true
		}
		return healthTruthy(health, "seatbelt_model_loaded") || healthTruthy(health, "driver_phone_model_loaded")
	}
	return false
}

// EnrichCatalogWithHealth enriches the catalog and marks activation_blocked when
// required models/OCR/face are missing from live AI health (A.4 honesty).
func EnrichCatalogWithHealth(templates []CatalogTemplate, reg *CapabilitiesRegistry, health map[string]string) []EnrichedCatalogTemplate {
	if reg == nil {
		reg = defaultRegistry()
	}
	out := make([]EnrichedCatalogTemplate, 0, len(templates))
	for _, t := range templates {
		e := EnrichedCatalogTemplate{CatalogTemplate: t, Supported: false}
		if tc, ok := reg.Templates[t.ID]; ok {
			e.CapabilityID = tc.CapabilityID
			e.HumanDescription = tc.HumanDescription
			e.RoleSummaryFR = tc.RoleSummaryFR
			e.Illustration = tc.Illustration
			e.DeploymentScopes = tc.DeploymentScopes
			e.Tutorial = tc.Tutorial
			e.Prerequisites = tc.Prerequisites
			if len(tc.ConfigSchema) > 0 {
				e.ConfigSchema = tc.ConfigSchema
			}
			if tc.Supported && templateHasConfigFields(tc.ConfigSchema) {
				e.Supported = true
			}
			e.UnsupportedMessageFR = tc.UnsupportedMessageFR
		}
		if e.CapabilityID == "" {
			ev := ExtractPrimaryEvent(t.Definition)
			e.CapabilityID = ev
			if e.HumanDescription == "" {
				if meta, ok := reg.EventTypes[ev]; ok {
					e.HumanDescription = meta.LabelFR
				}
			}
		}

		// Infer scope from category unless explicitly set in ai-capabilities.json.
		if len(e.DeploymentScopes) == 0 {
			e.DeploymentScopes = scopesForCategory(t.Category)
		}
		if e.RoleSummaryFR == "" {
			e.RoleSummaryFR = e.HumanDescription
		}

		if !e.Supported && e.UnsupportedMessageFR == "" {
			if meta, ok := reg.EventTypes[e.CapabilityID]; ok && meta.UnsupportedMessageFR != "" {
				e.UnsupportedMessageFR = meta.UnsupportedMessageFR
			} else if meta, ok := reg.EventTypes[e.CapabilityID]; ok && len(meta.Models) > 0 {
				e.UnsupportedMessageFR = fmt.Sprintf("Nécessite : %s", strings.Join(meta.Models, ", "))
			}
		}

		if health != nil {
			req := requiredHealthKeysForTemplate(t)
			var missing []string
			for _, k := range req {
				if !healthSatisfies(health, k) {
					missing = append(missing, k)
				}
			}
			if len(missing) > 0 {
				e.ActivationBlocked = true
				e.MissingHealthKeys = missing
				e.ActivationBlockReason = fmt.Sprintf(
					"Prérequis IA manquants (%s) — bridge Gemini (FRIGATE_VLM_BRIDGE+GEMINI_*) ou modèles ONNX requis.",
					strings.Join(missing, ", "),
				)
			}
		}

		out = append(out, e)
	}
	return out
}
