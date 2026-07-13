package aimodels

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/citevision/citevision-v2/backend/internal/ingest"
	"github.com/google/uuid"
)

type ModelEntry struct {
	ID        string `json:"id"`
	HealthKey string `json:"health_key"`
	Kind      string `json:"kind"`
	Required  bool   `json:"required"`
	LabelFR   string `json:"label_fr"`
	LabelEN   string `json:"label_en"`
	Behavior  string `json:"behavior,omitempty"`
	EventType string `json:"event_type,omitempty"`
	File      string `json:"file,omitempty"`
	Loaded    bool   `json:"loaded"`
	Notes     string `json:"notes,omitempty"`
}

type PackResponse struct {
	Version           int               `json:"version"`
	InstallCommand    string            `json:"install_command"`
	VerifyCommand     string            `json:"verify_command"`
	GPUHealthKey      string            `json:"gpu_health_key,omitempty"`
	GPULoaded         bool              `json:"gpu_loaded"`
	Models            []ModelEntry      `json:"models"`
	Health            map[string]string `json:"health"`
	DetectionClasses  []string          `json:"detection_classes,omitempty"`
	ClassFilterGroups map[string][]string `json:"class_filter_groups,omitempty"`
}

var primaryLabels = map[string]struct{ FR, EN string }{
	"yolo":        {"YOLO (détection)", "YOLO (detection)"},
	"insightface": {"Reconnaissance faciale", "Face recognition"},
	"paddleocr":   {"Lecture de plaques (OCR)", "License plate OCR"},
}

var secondaryLabels = map[string]struct{ FR, EN string }{
	"driver_phone": {"Téléphone au volant (ONNX)", "Driver phone (ONNX)"},
	"seatbelt":     {"Ceinture de sécurité (ONNX)", "Seatbelt (ONNX)"},
}

func healthTrue(health map[string]string, key string) bool {
	v, ok := health[key]
	if !ok {
		return false
	}
	return strings.EqualFold(v, "true") || v == "1"
}

// BuildPack merges shared registries with live AI /health and org custom models [Phase D].
func BuildPack(ctx context.Context, ai *ingest.AIClient, sharedPath string, orgID uuid.UUID) (*PackResponse, error) {
	regPath := filepath.Join(sharedPath, "ai-stack-registry.json")
	regData, err := os.ReadFile(regPath)
	if err != nil {
		return nil, fmt.Errorf("ai-stack-registry: %w", err)
	}
	var reg map[string]interface{}
	if err := json.Unmarshal(regData, &reg); err != nil {
		return nil, err
	}

	health := map[string]string{}
	if ai != nil {
		if h, err := ai.FetchHealth(ctx); err == nil {
			health = h
		}
	}

	suffix := "_model_loaded"
	if s, ok := reg["secondary_health_suffix"].(string); ok && s != "" {
		suffix = s
	}

	var models []ModelEntry
	if rawModels, ok := reg["models"].([]interface{}); ok {
		for _, raw := range rawModels {
			spec, _ := raw.(map[string]interface{})
			if spec == nil {
				continue
			}
			id := str(spec, "id")
			hk := str(spec, "health_key")
			if id == "" || hk == "" {
				continue
			}
			labels := primaryLabels[id]
			models = append(models, ModelEntry{
				ID:        id,
				HealthKey: hk,
				Kind:      strDefault(spec, "kind", "primary"),
				Required:  boolDefault(spec, "required", true),
				LabelFR:   labels.FR,
				LabelEN:   labels.EN,
				File:      str(spec, "file"),
				Loaded:    healthTrue(health, hk),
				Notes:     str(spec, "notes"),
			})
		}
	}

	secPath := filepath.Join(sharedPath, "ai-models.json")
	if secData, err := os.ReadFile(secPath); err == nil {
		var sec map[string]interface{}
		if json.Unmarshal(secData, &sec) == nil {
			if rawModels, ok := sec["models"].([]interface{}); ok {
				for _, raw := range rawModels {
					spec, _ := raw.(map[string]interface{})
					if spec == nil {
						continue
					}
					id := str(spec, "id")
					if id == "" {
						continue
					}
					hk := id + suffix
					labels := secondaryLabels[id]
					models = append(models, ModelEntry{
						ID:        id,
						HealthKey: hk,
						Kind:      "secondary",
						Required:  boolDefault(spec, "required", true),
						LabelFR:   labels.FR,
						LabelEN:   labels.EN,
						Behavior:  str(spec, "behavior"),
						EventType: str(spec, "event_type"),
						File:      str(spec, "file"),
						Loaded:    healthTrue(health, hk),
						Notes:     str(spec, "notes"),
					})
				}
			}
		}
	}

	if orgID != uuid.Nil {
		orgModels, _ := LoadOrgModels(orgID)
		for _, m := range orgModels {
			if !m.ProbeOK {
				continue
			}
			hk := OrgModelHealthKey(m.ID)
			models = append(models, ModelEntry{
				ID:        m.ID,
				HealthKey: hk,
				Kind:      "org_custom",
				Required:  false,
				LabelFR:   m.LabelFR,
				LabelEN:   m.LabelEN,
				Behavior:  m.Behavior,
				EventType: m.EventType,
				File:      m.File,
				Loaded:    healthTrue(health, hk),
				Notes:     m.HumanDescriptionFR,
			})
		}
	}

	gpuKey := str(reg, "gpu_health_key")
	classes, groups := detectionCatalog(sharedPath)
	return &PackResponse{
		Version:           intDefault(reg, "version", 1),
		InstallCommand:    str(reg, "install_command"),
		VerifyCommand:     str(reg, "verify_command"),
		GPUHealthKey:      gpuKey,
		GPULoaded:         healthTrue(health, gpuKey),
		Models:            models,
		Health:            health,
		DetectionClasses:  classes,
		ClassFilterGroups: groups,
	}, nil
}

var yoloCocoClasses = []string{
	"person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
	"traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
	"dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
}

func detectionCatalog(sharedPath string) ([]string, map[string][]string) {
	seen := map[string]struct{}{}
	var classes []string
	add := func(c string) {
		c = strings.TrimSpace(c)
		if c == "" {
			return
		}
		if _, ok := seen[c]; ok {
			return
		}
		seen[c] = struct{}{}
		classes = append(classes, c)
	}
	for _, c := range yoloCocoClasses {
		add(c)
	}
	secPath := filepath.Join(sharedPath, "ai-models.json")
	if secData, err := os.ReadFile(secPath); err == nil {
		var sec map[string]interface{}
		if json.Unmarshal(secData, &sec) == nil {
			if rawModels, ok := sec["models"].([]interface{}); ok {
				for _, raw := range rawModels {
					spec, _ := raw.(map[string]interface{})
					if spec == nil {
						continue
					}
					if rawCls, ok := spec["classes"].([]interface{}); ok {
						for _, rc := range rawCls {
							if s, ok := rc.(string); ok {
								add(s)
							}
						}
					}
				}
			}
		}
	}
	groups := map[string][]string{
		"person":   {"person"},
		"vehicle":  {"car", "truck", "bus", "motorcycle", "bicycle"},
		"animal":   {"bird", "cat", "dog", "horse", "sheep", "cow"},
	}
	return classes, groups
}

func str(m map[string]interface{}, key string) string {
	if v, ok := m[key].(string); ok {
		return v
	}
	return ""
}

func strDefault(m map[string]interface{}, key, def string) string {
	if v := str(m, key); v != "" {
		return v
	}
	return def
}

func boolDefault(m map[string]interface{}, key string, def bool) bool {
	if v, ok := m[key].(bool); ok {
		return v
	}
	return def
}

func intDefault(m map[string]interface{}, key string, def int) int {
	switch v := m[key].(type) {
	case float64:
		return int(v)
	case int:
		return v
	default:
		return def
	}
}
