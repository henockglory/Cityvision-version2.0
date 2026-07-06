package ingest

import (
	"context"
	"encoding/json"

	"github.com/google/uuid"
)

// CapabilityManifest is the single camera config object for the AI pipeline [K.97].
type CapabilityManifest struct {
	CameraID             string                   `json:"camera_id"`
	OrgID                string                   `json:"org_id"`
	Spatial              map[string]interface{}   `json:"spatial"`
	ActiveIntents        []map[string]interface{} `json:"active_intents"`
	ModelIDs             []string                 `json:"model_ids"`
	CapabilityProfiles   []map[string]interface{} `json:"capability_profiles"`
	EvidenceCaptureRules []map[string]interface{} `json:"evidence_capture_rules,omitempty"`
}

func (o *Orchestrator) buildCapabilityManifest(
	ctx context.Context,
	orgID, cameraID uuid.UUID,
	spatialCfg map[string]interface{},
	capProfiles []map[string]interface{},
	evidenceRules []map[string]interface{},
) CapabilityManifest {
	intents := o.buildActiveIntents(ctx, orgID, cameraID)
	models := collectModelIDs(spatialCfg, capProfiles)
	return CapabilityManifest{
		CameraID:             cameraID.String(),
		OrgID:                orgID.String(),
		Spatial:              spatialCfg,
		ActiveIntents:        intents,
		ModelIDs:             models,
		CapabilityProfiles:   capProfiles,
		EvidenceCaptureRules: evidenceRules,
	}
}

func (o *Orchestrator) buildActiveIntents(ctx context.Context, orgID, cameraID uuid.UUID) []map[string]interface{} {
	rows, err := o.pool.Query(ctx, `
		SELECT name, definition FROM rules
		WHERE org_id = $1 AND is_enabled = TRUE`, orgID)
	if err != nil {
		return nil
	}
	defer rows.Close()
	var out []map[string]interface{}
	for rows.Next() {
		var name string
		var def json.RawMessage
		if rows.Scan(&name, &def) != nil {
			continue
		}
		var m map[string]interface{}
		if json.Unmarshal(def, &m) != nil {
			continue
		}
		bindings, _ := m["bindings"].(map[string]interface{})
		cam := strField(bindings, "camera_id")
		if cam == "" {
			cam = strField(m, "camera_id")
		}
		if cam != "" && cam != cameraID.String() {
			continue
		}
		intent := map[string]interface{}{
			"rule_name":   name,
			"template_id": strField(bindings, "template_id"),
			"zone_name":   strField(bindings, "zone_name"),
			"line_name":   strField(bindings, "line_name"),
			"event_type":  extractEventType(m),
		}
		out = append(out, intent)
	}
	return out
}

func extractEventType(def map[string]interface{}) string {
	cond, ok := def["condition"].(map[string]interface{})
	if !ok {
		return ""
	}
	return extractEventFromCond(cond)
}

func extractEventFromCond(node map[string]interface{}) string {
	op, _ := node["op"].(string)
	field, _ := node["field"].(string)
	if op == "eq" && (field == "event_type" || field == "event") {
		if v, ok := node["value"].(string); ok {
			return v
		}
	}
	if children, ok := node["children"].([]interface{}); ok {
		for _, c := range children {
			if m, ok := c.(map[string]interface{}); ok {
				if ev := extractEventFromCond(m); ev != "" {
					return ev
				}
			}
		}
	}
	return ""
}

func collectModelIDs(spatial map[string]interface{}, profiles []map[string]interface{}) []string {
	seen := map[string]bool{}
	var out []string
	add := func(id string) {
		if id != "" && !seen[id] {
			seen[id] = true
			out = append(out, id)
		}
	}
	zones, _ := spatial["zones"].([]interface{})
	for _, z := range zones {
		m, ok := z.(map[string]interface{})
		if !ok {
			continue
		}
		behavior, _ := m["behavior"].(string)
		switch behavior {
		case "phone_use", "driver_cabin":
			add("driver_phone")
		case "seatbelt":
			add("seatbelt")
		case "plate_ocr":
			add("paddleocr")
		}
	}
	for _, p := range profiles {
		caps, _ := p["capabilities"].([]interface{})
		for _, c := range caps {
			if s, ok := c.(string); ok && s == "plate_ocr" {
				add("paddleocr")
			}
		}
	}
	return out
}
