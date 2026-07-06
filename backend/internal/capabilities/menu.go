package capabilities

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/citevision/citevision-v2/backend/internal/aimodels"
	"github.com/citevision/citevision-v2/backend/internal/ingest"
	"github.com/citevision/citevision-v2/backend/internal/rules"
	"github.com/google/uuid"
)

type BehaviorMenuItem struct {
	ID               string   `json:"id"`
	Group            string   `json:"group"`
	AppliesTo        string   `json:"applies_to"`
	LabelFR          string   `json:"label_fr"`
	LabelEN          string   `json:"label_en"`
	Capability       string   `json:"capability"`
	HumanDescription string   `json:"human_description_fr"`
	Emits            []string `json:"emits"`
	Requires         []string `json:"requires"`
	ConfigFields     json.RawMessage `json:"config_fields,omitempty"`
	Ready            bool     `json:"ready"`
	ReadyReasonFR    string   `json:"ready_reason_fr,omitempty"`
	CompatibleTemplates []string `json:"compatible_templates,omitempty"`
}

type MenuResponse struct {
	Behaviors []BehaviorMenuItem `json:"behaviors"`
	Health    map[string]string  `json:"health"`
}

type ZoneBehaviorsFile struct {
	Behaviors []ZoneBehaviorDef `json:"behaviors"`
}

type ZoneBehaviorDef struct {
	ID                 string          `json:"id"`
	Group              string          `json:"group"`
	AppliesTo          string          `json:"applies_to"`
	LabelFR            string          `json:"label_fr"`
	LabelEN            string          `json:"label_en"`
	Capability         string          `json:"capability"`
	HumanDescriptionFR string          `json:"human_description_fr"`
	Emits              []string        `json:"emits"`
	Requires           []string        `json:"requires"`
	ConfigFields       json.RawMessage `json:"config_fields"`
}

func LoadZoneBehaviors(sharedPath string) (*ZoneBehaviorsFile, error) {
	path := filepath.Join(sharedPath, "zone-behaviors.json")
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var f ZoneBehaviorsFile
	if err := json.Unmarshal(data, &f); err != nil {
		return nil, err
	}
	return &f, nil
}

func modelHealthKey(modelID string) string {
	switch modelID {
	case "driver_phone":
		return "driver_phone_model_loaded"
	case "seatbelt":
		return "seatbelt_model_loaded"
	case "paddleocr", "plate":
		return "plate_loaded"
	case "yolo":
		return "yolo_loaded"
	case "face", "insightface":
		return "face_loaded"
	default:
		return modelID + "_model_loaded"
	}
}

func healthTrue(health map[string]string, key string) bool {
	v, ok := health[key]
	if !ok {
		return false
	}
	return strings.EqualFold(v, "true") || v == "1"
}

func evaluateReady(requires []string, health map[string]string) (bool, string) {
	var missing []string
	for _, req := range requires {
		if strings.HasPrefix(req, "model:") {
			model := strings.TrimPrefix(req, "model:")
			if !healthTrue(health, modelHealthKey(model)) {
				missing = append(missing, "modèle "+model)
			}
			continue
		}
		if req == "polygon:edge_distances" {
			// readiness depends on zone geometry — checked at rule validation [K.96]
			continue
		}
		if strings.HasPrefix(req, "zone:") {
			// synergy checked at rule validation
			continue
		}
	}
	if len(missing) == 0 {
		return true, ""
	}
	return false, "Manque : " + strings.Join(missing, ", ")
}

func templatesForEmits(catalog []rules.CatalogTemplate, emits []string) []string {
	emitSet := map[string]bool{}
	for _, e := range emits {
		emitSet[e] = true
	}
	var out []string
	for _, t := range catalog {
		ev := rules.ExtractPrimaryEvent(t.Definition)
		if ev != "" && emitSet[ev] {
			out = append(out, t.ID)
		}
	}
	return out
}

// BuildMenu merges zone-behaviors + catalog + org custom models + AI health [K.94][J.88].
func BuildMenu(ctx context.Context, ai *ingest.AIClient, sharedPath, catalogPath string, orgID uuid.UUID) (*MenuResponse, error) {
	zb, err := LoadZoneBehaviors(sharedPath)
	if err != nil {
		return nil, fmt.Errorf("zone-behaviors: %w", err)
	}
	health := map[string]string{}
	if ai != nil {
		if h, err := ai.FetchHealth(ctx); err == nil {
			health = h
		}
	}
	catalog, _ := rules.LoadCatalog(catalogPath)
	items := make([]BehaviorMenuItem, 0, len(zb.Behaviors))
	for _, b := range zb.Behaviors {
		if b.ID == "" {
			continue
		}
		applies := b.AppliesTo
		if applies == "" {
			applies = "zone"
		}
		ready, reason := evaluateReady(b.Requires, health)
		items = append(items, BehaviorMenuItem{
			ID:               b.ID,
			Group:            b.Group,
			AppliesTo:        applies,
			LabelFR:          b.LabelFR,
			LabelEN:          b.LabelEN,
			Capability:       b.Capability,
			HumanDescription: b.HumanDescriptionFR,
			Emits:            b.Emits,
			Requires:         b.Requires,
			ConfigFields:     b.ConfigFields,
			Ready:            ready,
			ReadyReasonFR:    reason,
			CompatibleTemplates: templatesForEmits(catalog, b.Emits),
		})
	}

	if orgID != uuid.Nil {
		orgModels, _ := aimodels.LoadOrgModels(orgID)
		for _, m := range orgModels {
			if !m.ProbeOK {
				continue
			}
			behaviorID := m.Behavior
			if behaviorID == "" {
				behaviorID = "custom:" + m.ID
			}
			applies := m.AppliesTo
			if applies == "" {
				applies = "zone"
			}
			requires := []string{"model:" + m.ID}
			ready, reason := evaluateReady(requires, health)
			emits := []string{m.EventType}
			if m.EventType == "" {
				emits = []string{"custom_" + m.ID}
			}
			cap := m.Capability
			if cap == "" {
				cap = "beta"
			}
			desc := m.HumanDescriptionFR
			if desc == "" {
				desc = m.LabelFR
			}
			cfgFields, _ := json.Marshal([]map[string]interface{}{
				{"key": "confidence", "type": "number", "label_fr": "Confiance min", "label_en": "Min confidence", "default": 0.45, "min": 0.05, "max": 0.99, "step": 0.05},
			})
			items = append(items, BehaviorMenuItem{
				ID:                  behaviorID,
				Group:               "custom",
				AppliesTo:           applies,
				LabelFR:             m.LabelFR,
				LabelEN:             m.LabelEN,
				Capability:          cap,
				HumanDescription:    desc,
				Emits:               emits,
				Requires:            requires,
				ConfigFields:        cfgFields,
				Ready:               ready,
				ReadyReasonFR:       reason,
				CompatibleTemplates: templatesForEmits(catalog, emits),
			})
		}
	}

	return &MenuResponse{Behaviors: items, Health: health}, nil
}
