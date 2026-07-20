package evidence

import (
	"encoding/json"
	"strings"
)

// Policy mirrors rule.definition.evidence (frontend evidencePolicy.ts).
type Policy struct {
	Enabled     bool                     `json:"enabled"`
	ClipSeconds float64                  `json:"clip_seconds"`
	Images      []map[string]interface{} `json:"images"`
}

// Identification / plate_status — separate from violation proof (Phase A Tâche 4).
const (
	IdentificationVerified    = "verified"
	IdentificationUnreadable  = "unreadable"
	IdentificationMissing     = "missing"
	IdentificationNotRequired = "not_required"
)

// Violation status for the alert gate (clip + scene + subject).
const (
	ViolationConfirmed  = "violation_confirmed"
	ViolationIncomplete = "incomplete"
)

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
	case "tpl-line-cross", "tpl-line-cross-bidir",
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

func policyWantsPlate(policy Policy) bool {
	for _, im := range policy.Images {
		if role, _ := im["role"].(string); role == "plate" {
			return true
		}
	}
	return false
}

// violationRoles are hard requirements for alert persistence (never includes plate).
func violationRoles(policy Policy) []string {
	out := make([]string, 0, len(policy.Images))
	for _, im := range policy.Images {
		role, ok := im["role"].(string)
		if !ok || role == "" || role == "plate" {
			continue
		}
		out = append(out, role)
	}
	if len(out) == 0 {
		return []string{"scene", "subject"}
	}
	return out
}

// PlateStatus returns identification status. Never "verified" without extracted plate_number.
func PlateStatus(snap map[string]interface{}, policy Policy, plateNumber string) string {
	if !policy.Enabled || !policyWantsPlate(policy) {
		return IdentificationNotRequired
	}
	pkg := extractPackageMap(snap)
	hasPlateImg := false
	if pkg != nil {
		images, _ := pkg["images"].([]interface{})
		for _, im := range images {
			m, _ := im.(map[string]interface{})
			if m == nil {
				continue
			}
			if role, _ := m["role"].(string); role == "plate" && hasMediaRef(m) {
				hasPlateImg = true
				break
			}
		}
	}
	if strings.TrimSpace(plateNumber) != "" {
		return IdentificationVerified
	}
	if hasPlateImg {
		return IdentificationUnreadable
	}
	return IdentificationMissing
}

// ViolationStatusFromSnap returns violation_confirmed when clip+scene+subject are present.
func ViolationStatusFromSnap(snap map[string]interface{}, policy Policy) string {
	if !policy.Enabled {
		return ViolationConfirmed
	}
	if isViolationCompleteMap(snap, policy) {
		return ViolationConfirmed
	}
	return ViolationIncomplete
}

// AnnotateStatuses writes violation_status + plate_status / identification into the snapshot.
func AnnotateStatuses(snapshot json.RawMessage, policy Policy, plateNumber string) json.RawMessage {
	var snap map[string]interface{}
	if json.Unmarshal(snapshot, &snap) != nil || snap == nil {
		snap = map[string]interface{}{}
	}
	vStatus := ViolationStatusFromSnap(snap, policy)
	iStatus := PlateStatus(snap, policy, plateNumber)
	snap["violation_status"] = vStatus
	snap["plate_status"] = iStatus
	snap["identification"] = iStatus
	if pkg := extractPackageMap(snap); pkg != nil {
		meta, _ := pkg["metadata"].(map[string]interface{})
		if meta == nil {
			meta = map[string]interface{}{}
			pkg["metadata"] = meta
		}
		meta["violation_status"] = vStatus
		meta["plate_status"] = iStatus
		meta["identification"] = iStatus
		snap["package"] = pkg
	}
	b, _ := json.Marshal(snap)
	return b
}

// IsComplete checks *violation* proof (clip + scene + subject). Plate is not a hard gate.
func IsComplete(snapshot json.RawMessage, policy Policy) bool {
	if !policy.Enabled {
		return true
	}
	var snap map[string]interface{}
	if json.Unmarshal(snapshot, &snap) != nil || snap == nil {
		snap = map[string]interface{}{}
	}
	return isViolationCompleteMap(snap, policy)
}

func isViolationCompleteMap(snap map[string]interface{}, policy Policy) bool {
	if !policy.Enabled {
		return true
	}
	pkg := extractPackageMap(snap)
	if pkg == nil {
		return false
	}
	needRoles := violationRoles(policy)
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
	if policy.ClipSeconds > 0 {
		clip, _ := pkg["clip"].(map[string]interface{})
		if !hasMediaRef(clip) {
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
	return isViolationCompleteMap(snap, policy)
}

// IsCompleteMap checks a snapshot map (may include nested package).
func IsCompleteMap(snap map[string]interface{}, policy Policy) bool {
	return isViolationCompleteMap(snap, policy)
}

func requiredRoles(policy Policy) []string {
	out := make([]string, 0, len(policy.Images))
	for _, im := range policy.Images {
		role, ok := im["role"].(string)
		if ok && role != "" {
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
