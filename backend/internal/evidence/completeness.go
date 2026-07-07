package evidence

import (
	"encoding/json"
)

// Policy mirrors rule.definition.evidence (frontend evidencePolicy.ts).
type Policy struct {
	Enabled     bool                     `json:"enabled"`
	ClipSeconds float64                  `json:"clip_seconds"`
	Images      []map[string]interface{} `json:"images"`
}

// DefaultPolicy matches DEFAULT_EVIDENCE_POLICY in the frontend.
func DefaultPolicy() Policy {
	return Policy{
		Enabled:     true,
		ClipSeconds: 6,
		Images: []map[string]interface{}{
			{"role": "scene"},
			{"role": "subject"},
		},
	}
}

// CountingPolicy matches COUNTING_EVIDENCE_POLICY — line_cross alerts need no clip/images.
func CountingPolicy() Policy {
	return Policy{Enabled: false, ClipSeconds: 0, Images: nil}
}

func templateIDFromDefinition(root map[string]interface{}) string {
	bindings, _ := root["bindings"].(map[string]interface{})
	if bindings == nil {
		return ""
	}
	id, _ := bindings["template_id"].(string)
	return id
}

func isCountingTemplate(templateID string) bool {
	switch templateID {
	case "tpl-line-cross", "tpl-line-cross-bidir", "tpl-speeding-premium",
		"tpl-observation-rule-set-or", "tpl-observation-rule-set-n":
		return true
	default:
		return false
	}
}

func observationModeFromDefinition(root map[string]interface{}) bool {
	bindings, _ := root["bindings"].(map[string]interface{})
	if bindings == nil {
		return false
	}
	v, _ := bindings["observation_mode"].(bool)
	return v
}

// PolicyFromDefinition extracts evidence policy from a rule definition JSON blob.
func PolicyFromDefinition(definition json.RawMessage) Policy {
	if len(definition) == 0 {
		return DefaultPolicy()
	}
	var root map[string]interface{}
	if json.Unmarshal(definition, &root) != nil {
		return DefaultPolicy()
	}
	tplID := templateIDFromDefinition(root)
	if observationModeFromDefinition(root) {
		return CountingPolicy()
	}
	raw, ok := root["evidence"]
	if !ok || raw == nil {
		if isCountingTemplate(tplID) {
			return CountingPolicy()
		}
		return DefaultPolicy()
	}
	b, err := json.Marshal(raw)
	if err != nil {
		if isCountingTemplate(tplID) {
			return CountingPolicy()
		}
		return DefaultPolicy()
	}
	var p Policy
	if json.Unmarshal(b, &p) != nil {
		if isCountingTemplate(tplID) {
			return CountingPolicy()
		}
		return DefaultPolicy()
	}
	if !p.Enabled {
		return CountingPolicy()
	}
	if len(p.Images) == 0 {
		dp := DefaultPolicy()
		p.Images = dp.Images
	}
	if p.ClipSeconds == 0 {
		p.ClipSeconds = DefaultPolicy().ClipSeconds
	}
	return p
}

// PolicyRequiresProof is true when evidence capture is enabled on the rule.
func PolicyRequiresProof(p Policy) bool {
	return p.Enabled
}

// RequiredSlotCount returns clip (0 or 1) + configured image slots.
func RequiredSlotCount(p Policy) int {
	if !p.Enabled {
		return 0
	}
	n := 0
	if p.ClipSeconds > 0 {
		n++
	}
	n += len(p.Images)
	return n
}

// IsComplete checks snapshot JSON against policy (metadata: url or asset_id per slot).
func IsComplete(snapshot json.RawMessage, policy Policy) bool {
	if !policy.Enabled {
		return true
	}
	var snap map[string]interface{}
	if json.Unmarshal(snapshot, &snap) != nil || snap == nil {
		snap = map[string]interface{}{}
	}
	return isCompleteMap(snap, policy)
}

func isCompleteMap(snap map[string]interface{}, policy Policy) bool {
	if !policy.Enabled {
		return true
	}
	pkg := extractPackageMap(snap)
	if pkg == nil {
		return false
	}
	if policy.ClipSeconds > 0 {
		clip, _ := pkg["clip"].(map[string]interface{})
		if !hasMediaRef(clip) {
			return false
		}
	}
	needRoles := requiredRoles(policy)
	if len(needRoles) == 0 {
		return true
	}
	images, _ := pkg["images"].([]interface{})
	roles := map[string]bool{}
	for _, im := range images {
		m, _ := im.(map[string]interface{})
		if m == nil {
			continue
		}
		role, _ := m["role"].(string)
		if role != "" && hasMediaRef(m) {
			roles[role] = true
		}
	}
	for _, r := range needRoles {
		if !roles[r] {
			return false
		}
	}
	return true
}

// IsCompleteFromPayload checks event/alert payload before snapshot normalization.
func IsCompleteFromPayload(payload map[string]interface{}, policy Policy) bool {
	if !policy.Enabled {
		return true
	}
	snap := map[string]interface{}{}
	if pkg := extractPackageFromMap(payload); pkg != nil {
		snap["package"] = pkg
	}
	return isCompleteMap(snap, policy)
}

// IsCompleteMap checks a snapshot map (may include nested package).
func IsCompleteMap(snap map[string]interface{}, policy Policy) bool {
	return isCompleteMap(snap, policy)
}

func requiredRoles(policy Policy) []string {
	out := make([]string, 0, len(policy.Images))
	for _, im := range policy.Images {
		if role, ok := im["role"].(string); ok && role != "" {
			out = append(out, role)
		}
	}
	return out
}

func hasMediaRef(m map[string]interface{}) bool {
	if m == nil {
		return false
	}
	if u, ok := m["url"].(string); ok && u != "" {
		return true
	}
	if id, ok := m["asset_id"].(string); ok && id != "" {
		return true
	}
	return false
}

func extractPackageMap(snap map[string]interface{}) map[string]interface{} {
	if pkg, ok := snap["package"].(map[string]interface{}); ok && pkg != nil {
		return pkg
	}
	if ev, ok := snap["evidence"].(map[string]interface{}); ok {
		if pkg, ok := ev["package"].(map[string]interface{}); ok {
			return pkg
		}
	}
	return nil
}

func extractPackageFromMap(payload map[string]interface{}) map[string]interface{} {
	if payload == nil {
		return nil
	}
	if pkg, ok := payload["package"].(map[string]interface{}); ok {
		return pkg
	}
	if ev, ok := payload["evidence"].(map[string]interface{}); ok {
		if pkg, ok := ev["package"].(map[string]interface{}); ok {
			return pkg
		}
	}
	return extractPackageMap(payload)
}

// IsDemoDefinition is true when rule.definition.bindings.demo is set.
func IsDemoDefinition(definition json.RawMessage) bool {
	if len(definition) == 0 {
		return false
	}
	var root map[string]interface{}
	if json.Unmarshal(definition, &root) != nil {
		return false
	}
	bindings, _ := root["bindings"].(map[string]interface{})
	if bindings == nil {
		return false
	}
	if d, ok := bindings["demo"].(bool); ok && d {
		return true
	}
	if ds, ok := bindings["demo"].(string); ok && ds == "true" {
		return true
	}
	return false
}

// HasSceneEvidence returns true when the snapshot includes a scene image reference.
func HasSceneEvidence(snapshot json.RawMessage) bool {
	var snap map[string]interface{}
	if json.Unmarshal(snapshot, &snap) != nil || snap == nil {
		return false
	}
	pkg := extractPackageMap(snap)
	if pkg == nil {
		return false
	}
	images, _ := pkg["images"].([]interface{})
	for _, im := range images {
		m, _ := im.(map[string]interface{})
		if m == nil {
			continue
		}
		role, _ := m["role"].(string)
		if role == "scene" && hasMediaRef(m) {
			return true
		}
	}
	return false
}
