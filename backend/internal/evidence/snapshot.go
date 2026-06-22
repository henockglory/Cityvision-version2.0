package evidence

import (
	"encoding/json"
)

// MergeIntoSnapshot copies package + metadata fields into an evidence snapshot map.
func MergeIntoSnapshot(existing map[string]interface{}, pkg *Package, meta map[string]interface{}) json.RawMessage {
	out := map[string]interface{}{}
	for k, v := range existing {
		out[k] = v
	}
	if pkg != nil {
		out["package"] = pkg
	}
	copyKeys(meta, out, "bbox", "confidence", "track_id", "zone_id", "line_id",
		"plate_number", "face_label", "event_type", "speed_kmh", "direction",
		"class_name", "person_count", "vehicle_count", "clip_path", "camera_id")
	if pkg != nil && pkg.Clip != nil && pkg.Clip.URL != "" {
		out["clip_path"] = pkg.Clip.URL
	}
	b, _ := json.Marshal(out)
	return b
}

func ExtractPackageFromPayload(payload map[string]interface{}) *Package {
	if payload == nil {
		return nil
	}
	if ev, ok := payload["evidence"].(map[string]interface{}); ok {
		if raw, ok := ev["package"]; ok {
			return parsePackage(raw)
		}
	}
	if raw, ok := payload["package"]; ok {
		return parsePackage(raw)
	}
	return nil
}

func SnapshotFromPayload(payload map[string]interface{}) json.RawMessage {
	meta := map[string]interface{}{}
	copyKeys(payload, meta, "bbox", "confidence", "track_id", "zone_id", "line_id",
		"plate_number", "face_label", "event_type", "speed_kmh", "direction",
		"class_name", "person_count", "vehicle_count", "clip_path", "camera_id")
	if ev, ok := payload["evidence"].(map[string]interface{}); ok {
		copyKeys(ev, meta, "bbox", "confidence")
		if pkg := parsePackage(ev["package"]); pkg != nil {
			return MergeIntoSnapshot(meta, pkg, meta)
		}
	}
	if pkg := ExtractPackageFromPayload(payload); pkg != nil {
		return MergeIntoSnapshot(meta, pkg, meta)
	}
	b, _ := json.Marshal(meta)
	return b
}

func parsePackage(raw interface{}) *Package {
	if raw == nil {
		return nil
	}
	b, err := json.Marshal(raw)
	if err != nil {
		return nil
	}
	var pkg Package
	if json.Unmarshal(b, &pkg) != nil || pkg.Version == 0 {
		return nil
	}
	return &pkg
}

func copyKeys(src, dst map[string]interface{}, keys ...string) {
	for _, k := range keys {
		if v, ok := src[k]; ok && v != nil {
			dst[k] = v
		}
	}
}
