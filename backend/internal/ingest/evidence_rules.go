package ingest

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/google/uuid"
)

func (o *Orchestrator) buildEvidenceCaptureRulesForCamera(ctx context.Context, orgID, cameraID uuid.UUID) []map[string]interface{} {
	rows, err := o.pool.Query(ctx, `
		SELECT id, definition FROM rules
		WHERE org_id = $1 AND is_enabled = TRUE`, orgID)
	if err != nil {
		return nil
	}
	defer rows.Close()

	camStr := cameraID.String()
	var out []map[string]interface{}
	for rows.Next() {
		var id uuid.UUID
		var defRaw []byte
		if err := rows.Scan(&id, &defRaw); err != nil {
			continue
		}
		var def map[string]interface{}
		if err := json.Unmarshal(defRaw, &def); err != nil {
			continue
		}
		if !ruleAppliesToCamera(def, camStr) {
			continue
		}
		for _, target := range buildEvidenceCaptureRules(def, id.String()) {
			out = append(out, target)
		}
	}
	return out
}

// buildEvidenceCaptureRules derives AI capture targets from enabled rules with alert actions.
func buildEvidenceCaptureRules(def map[string]interface{}, ruleID string) []map[string]interface{} {
	if !ruleHasAlertAction(def) {
		return nil
	}
	target := extractEvidenceTarget(def)
	if target.eventType == "" {
		return nil
	}
	evidence := mergeEvidencePolicy(def)
	if bindings, ok := def["bindings"].(map[string]interface{}); ok {
		if cf, ok := bindings["class_filter"].(string); ok && cf != "" && target.classFilter == "" {
			target.classFilter = cf
		}
	}
	out := map[string]interface{}{
		"rule_id":    ruleID,
		"event_type": target.eventType,
		"enabled":    true,
		"evidence":   evidence,
	}
	if target.zoneID != "" {
		out["zone_id"] = target.zoneID
	}
	if target.classFilter != "" {
		out["class_filter"] = target.classFilter
	}
	return []map[string]interface{}{out}
}

type evidenceTarget struct {
	eventType   string
	zoneID      string
	classFilter string
}

func defaultEvidencePolicy() map[string]interface{} {
	return map[string]interface{}{
		"enabled":      true,
		"clip_seconds": 6,
		"images": []map[string]interface{}{
			{"role": "scene", "label": "Vue d'ensemble", "crop": "full"},
			{"role": "subject", "label": "Cible détectée", "crop": "bbox", "padding_pct": 10, "zoom": 1.0},
		},
		"min_confidence": 0.0,
	}
}

func ruleHasAlertAction(def map[string]interface{}) bool {
	actions, ok := def["actions"].([]interface{})
	if !ok {
		return false
	}
	for _, a := range actions {
		m, ok := a.(map[string]interface{})
		if !ok {
			continue
		}
		if t, _ := m["type"].(string); t == "alert" {
			return true
		}
	}
	return false
}

func extractEvidenceTarget(def map[string]interface{}) evidenceTarget {
	var t evidenceTarget
	if cond, ok := def["condition"].(map[string]interface{}); ok {
		walkCondition(cond, &t)
	}
	if bindings, ok := def["bindings"].(map[string]interface{}); ok {
		if z, ok := bindings["zone_name"].(string); ok && z != "" && t.zoneID == "" {
			t.zoneID = z
		}
		if cf, ok := bindings["class_filter"].(string); ok && cf != "" && t.classFilter == "" {
			t.classFilter = cf
		}
	}
	return t
}

func walkCondition(node map[string]interface{}, t *evidenceTarget) {
	if node == nil {
		return
	}
	op, _ := node["op"].(string)
	switch op {
	case "eq":
		field, _ := node["field"].(string)
		val := fmt.Sprint(node["value"])
		switch field {
		case "event_type", "event":
			if t.eventType == "" {
				t.eventType = val
			}
		case "zone_id":
			t.zoneID = val
		case "class_name":
			t.classFilter = val
		}
	case "matches_class":
		t.classFilter = fmt.Sprint(node["value"])
	}
	children, _ := node["children"].([]interface{})
	for _, c := range children {
		if cm, ok := c.(map[string]interface{}); ok {
			walkCondition(cm, t)
		}
	}
}

func mergeEvidencePolicy(def map[string]interface{}) map[string]interface{} {
	out := defaultEvidencePolicy()
	raw, ok := def["evidence"].(map[string]interface{})
	if !ok {
		return out
	}
	for k, v := range raw {
		out[k] = v
	}
	if imgs, ok := raw["images"].([]interface{}); ok && len(imgs) > 0 {
		out["images"] = imgs
	}
	return out
}
