package alerts

import (
	"encoding/json"
	"strings"

	"github.com/citevision/citevision-v2/backend/internal/evidence"
)

// BuildEvidenceSnapshot extracts proof fields from MQTT / rule metadata for storage.
func BuildEvidenceSnapshot(meta map[string]interface{}) json.RawMessage {
	if meta == nil {
		return json.RawMessage(`{}`)
	}
	out := map[string]interface{}{}
	copyKeys(meta, out, "bbox", "confidence", "track_id", "zone_id", "line_id",
		"plate_number", "face_label", "event_type", "speed_kmh", "direction",
		"person_count", "vehicle_count", "clip_path", "camera_id", "class_name", "package")
	if payload, ok := meta["payload"].(map[string]interface{}); ok {
		copyKeys(payload, out, "bbox", "confidence", "track_id", "zone_id", "plate_number", "face_label", "event_type", "speed_kmh", "class_name")
		if ev, ok := payload["evidence"].(map[string]interface{}); ok {
			if pkg, ok := ev["package"]; ok {
				out["package"] = pkg
			}
		}
	}
	if ev, ok := meta["evidence"].(map[string]interface{}); ok {
		if pkg, ok := ev["package"]; ok {
			out["package"] = pkg
		}
		copyKeys(ev, out, "bbox", "confidence")
	}
	if es, ok := meta["evidence_snapshot"].(map[string]interface{}); ok {
		for k, v := range es {
			if v != nil {
				out[k] = v
			}
		}
	}
	if clip, ok := meta["clip_path"].(string); ok && clip != "" {
		out["clip_path"] = clip
	}
	if pkg := evidence.ExtractPackageFromPayload(meta); pkg != nil {
		return evidence.MergeIntoSnapshot(out, pkg, out)
	}
	b, _ := json.Marshal(out)
	return b
}

func copyKeys(src, dst map[string]interface{}, keys ...string) {
	for _, k := range keys {
		if v, ok := src[k]; ok && v != nil {
			dst[k] = v
		}
	}
}

// EnrichCreateMetadata merges evidence into alert metadata at ingest time.
func EnrichCreateMetadata(meta json.RawMessage) json.RawMessage {
	var m map[string]interface{}
	if err := json.Unmarshal(meta, &m); err != nil || m == nil {
		m = map[string]interface{}{}
	}

	promoteIdentityFields(m)

	ev := BuildEvidenceSnapshot(m)
	var evMap map[string]interface{}
	_ = json.Unmarshal(ev, &evMap)
	m["evidence_snapshot"] = evMap

	b, _ := json.Marshal(m)
	return b
}

func promoteIdentityFields(m map[string]interface{}) {
	if payload, ok := m["payload"].(map[string]interface{}); ok {
		for _, pair := range []struct{ src, dst string }{
			{"plate_number", "plate_number"},
			{"plate", "plate_number"},
			{"label", "face_label"},
			{"identifier", "face_label"},
		} {
			if v, ok := payload[pair.src].(string); ok && strings.TrimSpace(v) != "" {
				if existing, ok := m[pair.dst].(string); !ok || strings.TrimSpace(existing) == "" {
					m[pair.dst] = strings.TrimSpace(v)
				}
			}
		}
	}
	for _, pair := range []struct{ src, dst string }{
		{"plate_number", "plate_number"},
		{"plate", "plate_number"},
		{"label", "face_label"},
		{"identifier", "face_label"},
	} {
		if v, ok := m[pair.src].(string); ok && strings.TrimSpace(v) != "" {
			if existing, ok := m[pair.dst].(string); !ok || strings.TrimSpace(existing) == "" {
				m[pair.dst] = strings.TrimSpace(v)
			}
		}
	}
}
