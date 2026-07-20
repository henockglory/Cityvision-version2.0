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
	RoleSummaryFR       string   `json:"role_summary_fr,omitempty"`
	Illustration        string   `json:"illustration,omitempty"`
	DeploymentScopes    []string `json:"deployment_scopes,omitempty"`
	Tutorial             string   `json:"tutorial,omitempty"`
	Prerequisites        []string `json:"prerequisites,omitempty"`
	UnsupportedMessageFR string   `json:"unsupported_message_fr,omitempty"`
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
		out = append(out, e)
	}
	return out
}
