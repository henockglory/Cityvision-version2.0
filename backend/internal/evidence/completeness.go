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
	FailClosed  []string                 `json:"fail_closed,omitempty"`
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

// DefaultPolicy matches DEFAULT_EVIDENCE_POLICY in the frontend (road archetype).
func DefaultPolicy() Policy {
	return Policy{
		Enabled:     true,
		ClipSeconds: 6,
		Images: []map[string]interface{}{
			{"role": "scene"},
			{"role": "subject"},
			{"role": "plate"},
		},
		FailClosed: []string{"subject", "plate"},
	}
}

// CountingPolicy matches COUNTING_EVIDENCE_POLICY — line_cross alerts need no clip/images.
func CountingPolicy() Policy {
	return Policy{Enabled: false, ClipSeconds: 0, Images: nil, FailClosed: nil}
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

func failClosedFromRaw(raw map[string]interface{}) []string {
	arr, ok := raw["fail_closed"].([]interface{})
	if !ok || len(arr) == 0 {
		return nil
	}
	out := make([]string, 0, len(arr))
	for _, v := range arr {
		s, _ := v.(string)
		s = strings.TrimSpace(strings.ToLower(s))
		if s != "" {
			out = append(out, s)
		}
	}
	return out
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
	rawMap, _ := raw.(map[string]interface{})
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
	// Preserve explicit clip_seconds=0 (cabin VLM). Only default when key absent.
	if rawMap != nil {
		if _, hasClip := rawMap["clip_seconds"]; !hasClip && p.ClipSeconds == 0 {
			p.ClipSeconds = DefaultPolicy().ClipSeconds
		}
		if len(p.FailClosed) == 0 {
			p.FailClosed = failClosedFromRaw(rawMap)
		}
	} else if p.ClipSeconds == 0 {
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

func failClosedSet(policy Policy) map[string]bool {
	out := map[string]bool{}
	for _, r := range policy.FailClosed {
		r = strings.TrimSpace(strings.ToLower(r))
		if r != "" {
			out[r] = true
		}
	}
	// Contract often lists plate in images without repeating fail_closed in older rules —
	// only hard-gate plate when explicitly listed in fail_closed.
	return out
}

// violationRoles are hard requirements for alert persistence.
// Plate is included only when fail_closed contains "plate".
func violationRoles(policy Policy) []string {
	fc := failClosedSet(policy)
	out := make([]string, 0, len(policy.Images))
	for _, im := range policy.Images {
		role, ok := im["role"].(string)
		if !ok || role == "" {
			continue
		}
		role = strings.ToLower(role)
		if role == "plate" && !fc["plate"] {
			continue
		}
		out = append(out, role)
	}
	if len(out) == 0 {
		return []string{"scene", "subject"}
	}
	// If fail_closed is set, require those roles (plus non-plate images already collected).
	if len(fc) > 0 {
		seen := map[string]bool{}
		merged := make([]string, 0, len(out)+len(fc))
		for _, r := range out {
			if !seen[r] {
				seen[r] = true
				merged = append(merged, r)
			}
		}
		for r := range fc {
			if !seen[r] {
				seen[r] = true
				merged = append(merged, r)
			}
		}
		return merged
	}
	return out
}

func plateNumberFromSnap(snap map[string]interface{}) string {
	if snap == nil {
		return ""
	}
	if s, ok := snap["plate_number"].(string); ok && strings.TrimSpace(s) != "" {
		return strings.TrimSpace(s)
	}
	if pkg := extractPackageMap(snap); pkg != nil {
		if meta, ok := pkg["metadata"].(map[string]interface{}); ok {
			if s, ok := meta["plate_number"].(string); ok && strings.TrimSpace(s) != "" {
				return strings.TrimSpace(s)
			}
		}
	}
	return ""
}

func hasPlateProof(snap map[string]interface{}, pkg map[string]interface{}) bool {
	if strings.TrimSpace(plateNumberFromSnap(snap)) != "" {
		return true
	}
	if pkg == nil {
		return false
	}
	images, _ := pkg["images"].([]interface{})
	for _, im := range images {
		m, _ := im.(map[string]interface{})
		if m == nil {
			continue
		}
		if role, _ := m["role"].(string); role == "plate" && hasMediaRef(m) {
			return true
		}
	}
	return false
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

// ViolationStatusFromSnap returns violation_confirmed when clip+required roles are present.
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
	if strings.TrimSpace(plateNumber) != "" {
		snap["plate_number"] = strings.TrimSpace(plateNumber)
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
		if strings.TrimSpace(plateNumber) != "" {
			meta["plate_number"] = strings.TrimSpace(plateNumber)
		}
		snap["package"] = pkg
	}
	b, _ := json.Marshal(snap)
	return b
}

// IsComplete checks violation proof including fail_closed plate / face / reference.
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
	fc := failClosedSet(policy)
	images, _ := pkg["images"].([]interface{})
	roles := map[string]bool{}
	for _, im := range images {
		m, _ := im.(map[string]interface{})
		if m == nil {
			continue
		}
		role, _ := m["role"].(string)
		if role != "" && hasMediaRef(m) {
			roles[strings.ToLower(role)] = true
		}
	}
	// Cabin / Gemini: exact VLM crop as scene(+subject) is sufficient proof —
	// no clip is expected (crop bytes are what Gemini judged).
	if pkgMeta, ok := pkg["metadata"].(map[string]interface{}); ok {
		src, _ := pkgMeta["capture_source"].(string)
		if strings.EqualFold(strings.TrimSpace(src), "gemini_vlm_crop") && roles["scene"] {
			if fc["subject"] && !(roles["subject"] || roles["face"]) {
				return false
			}
			return true
		}
		// Face identity: crop + optional/hard reference; face and subject are aliases.
		if strings.EqualFold(strings.TrimSpace(src), "face_identity") {
			if roles["face"] {
				roles["subject"] = true
			}
			if roles["subject"] {
				roles["face"] = true
			}
			if fc["face"] && !(roles["face"] || roles["subject"]) {
				return false
			}
			if fc["reference"] && !roles["reference"] {
				return false
			}
			if (roles["face"] || roles["subject"]) && (roles["scene"] || roles["face"] || roles["subject"]) {
				if policy.ClipSeconds <= 0 {
					return true
				}
				clip, _ := pkg["clip"].(map[string]interface{})
				if hasMediaRef(clip) {
					return true
				}
				// Soft-complete when face present so Alertes shows the match (clip may be late).
				if roles["face"] || roles["subject"] {
					if !fc["reference"] || roles["reference"] {
						return true
					}
				}
			}
		}
	}
	// face ↔ subject alias for tpl-face-watchlist policies.
	if roles["face"] {
		roles["subject"] = true
	}
	if roles["subject"] {
		roles["face"] = true
	}
	for _, r := range needRoles {
		r = strings.ToLower(r)
		if r == "plate" {
			if !hasPlateProof(snap, pkg) {
				return false
			}
			continue
		}
		if r == "reference" {
			// Hard only when fail_closed lists reference.
			if fc["reference"] && !roles["reference"] {
				return false
			}
			if !fc["reference"] {
				continue
			}
		}
		if !roles[r] {
			return false
		}
	}
	if policy.ClipSeconds > 0 {
		clip, _ := pkg["clip"].(map[string]interface{})
		if !hasMediaRef(clip) {
			// Soft clip only for face_identity (handled above); otherwise hard.
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
	if pn, ok := payload["plate_number"].(string); ok && pn != "" {
		snap["plate_number"] = pn
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
