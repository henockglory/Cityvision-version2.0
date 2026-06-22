package ingest

import (
	"context"
	"encoding/json"

	"github.com/google/uuid"
)

// buildCapabilityProfiles derives AI capability gating from active rules (pipeline + presence).
func (o *Orchestrator) buildCapabilityProfiles(ctx context.Context, orgID, cameraID uuid.UUID) []map[string]interface{} {
	rows, err := o.pool.Query(ctx, `
		SELECT definition FROM rules
		WHERE org_id = $1 AND is_enabled = TRUE`, orgID)
	if err != nil {
		return nil
	}
	defer rows.Close()

	var out []map[string]interface{}
	seen := map[string]bool{}

	for rows.Next() {
		var def json.RawMessage
		if err := rows.Scan(&def); err != nil {
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

		if pipe, ok := m["pipeline"].(map[string]interface{}); ok {
			profile := map[string]interface{}{
				"trigger": pipe["trigger"],
				"stages":  pipe["stages"],
			}
			if z := strField(bindings, "zone_name"); z != "" {
				profile["zone_id"] = z
			}
			if cf := strField(bindings, "class_filter"); cf != "" {
				profile["class_filter"] = cf
			}
			key := cam + "|" + strField(bindings, "zone_name") + "|" + strField(bindings, "class_filter")
			if !seen[key] {
				seen[key] = true
				out = append(out, profile)
			}
			continue
		}

		tpl := strField(bindings, "template_id")
		if tpl == "tpl-zone-presence" || tpl == "tpl-traffic-corridor" {
			profile := map[string]interface{}{
				"zone_id":      strField(bindings, "zone_name"),
				"class_filter": strField(bindings, "class_filter"),
				"capabilities": []string{"plate_ocr", "speed_estimate", "evidence_capture"},
			}
			key := cam + "|" + strField(bindings, "zone_name") + "|" + strField(bindings, "class_filter")
			if !seen[key] {
				seen[key] = true
				out = append(out, profile)
			}
		}
	}
	if out == nil {
		out = []map[string]interface{}{}
	}
	return out
}

func strField(m map[string]interface{}, key string) string {
	if m == nil {
		return ""
	}
	if v, ok := m[key].(string); ok {
		return v
	}
	return ""
}
