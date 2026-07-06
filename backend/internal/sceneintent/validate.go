package sceneintent

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/google/uuid"

	"github.com/citevision/citevision-v2/backend/internal/capabilities"
	"github.com/citevision/citevision-v2/backend/internal/ingest"
	"github.com/citevision/citevision-v2/backend/internal/rules"
	"github.com/citevision/citevision-v2/backend/internal/spatial"
)

// ValidateDefinition checks cross-cutting scene intent constraints [K.96].
func ValidateDefinition(
	ctx context.Context,
	orgID uuid.UUID,
	definition json.RawMessage,
	spatialSvc *spatial.Service,
	ai *ingest.AIClient,
	sharedPath string,
) ValidationResult {
	var root map[string]interface{}
	if err := json.Unmarshal(definition, &root); err != nil {
		return ValidationResult{Valid: false, Errors: []string{"définition JSON invalide"}}
	}
	bindings, _ := root["bindings"].(map[string]interface{})
	cameraID := str(bindings, "camera_id")
	if cameraID == "" {
		cameraID = str(root, "camera_id")
	}
	zoneName := str(bindings, "zone_name")
	lineName := str(bindings, "line_name")
	tpl := str(bindings, "template_id")
	eventType := rules.ExtractPrimaryEvent(definition)

	var errs []string
	var warns []string

	health := map[string]string{}
	if ai != nil {
		if h, err := ai.FetchHealth(ctx); err == nil {
			health = h
		}
	}
	zb, _ := capabilities.LoadZoneBehaviors(sharedPath)

	// Model requirements for cabin / ANPR templates.
	switch tpl {
	case "tpl-phone-driving":
		if !healthOK(health, "driver_phone_model_loaded") {
			errs = append(errs, "modèle téléphone (driver_phone) non chargé — activez la zone phone_use et vérifiez /health")
		}
	case "tpl-seatbelt":
		if !healthOK(health, "seatbelt_model_loaded") {
			errs = append(errs, "modèle ceinture (seatbelt) non chargé — vérifiez /health")
		}
	}

	if tpl == "tpl-red-light" || eventType == "red_light_violation" {
		if !hasBehaviorOnCamera(ctx, spatialSvc, orgID, cameraID, "traffic_light_color") {
			errs = append(errs, "feu rouge : une zone traffic_light_color est requise sur la même caméra")
		}
		if zoneName == "" {
			warns = append(warns, "feu rouge : zone d'observation (red_light_observation) non liée dans bindings.zone_name")
		}
	}

	if tpl == "tpl-speeding-premium" || eventType == "speeding" {
		if zoneName != "" && !zoneHasCalibratedEdge(ctx, spatialSvc, orgID, zoneName) {
			errs = append(errs, "vitesse : calibrez au moins une arête (distance_to_next_m) sur la zone "+zoneName)
		}
	}

	// Behavior emits ↔ rule event_type [K.95].
	if zoneName != "" && eventType != "" && zb != nil {
		behavior := zoneBehaviorForName(ctx, spatialSvc, orgID, zoneName)
		if behavior != "" && !behaviorEmits(zb, behavior, eventType) {
			errs = append(errs, fmt.Sprintf(
				"incompatibilité : la zone %s (%s) n'émet pas %s",
				zoneName, behavior, eventType,
			))
		}
	}
	if lineName != "" && eventType == "line_cross" {
		// line_cross is always emitted by line_cross behavior
	}

	// class_filter coherence.
	if cf := str(bindings, "class_filter"); cf != "" && zoneName != "" {
		zcf := zoneClassFilter(ctx, spatialSvc, orgID, zoneName)
		if zcf != "" && zcf != "any" && cf != zcf {
			warns = append(warns, fmt.Sprintf(
				"class_filter règle (%s) différent de la zone (%s) — la zone fait foi [C.30]",
				cf, zcf,
			))
		}
	}

	return ValidationResult{
		Valid:    len(errs) == 0,
		Errors:   errs,
		Warnings: warns,
	}
}

func str(m map[string]interface{}, key string) string {
	if m == nil {
		return ""
	}
	if v, ok := m[key].(string); ok {
		return v
	}
	return ""
}

func healthOK(health map[string]string, key string) bool {
	v, ok := health[key]
	if !ok {
		return false
	}
	return strings.EqualFold(v, "true") || v == "1"
}

func parseBehaviorConfig(raw json.RawMessage) (string, map[string]interface{}) {
	if len(raw) == 0 {
		return "", nil
	}
	var m map[string]interface{}
	if json.Unmarshal(raw, &m) != nil {
		return "", nil
	}
	behavior, _ := m["behavior"].(string)
	cfg, _ := m["config"].(map[string]interface{})
	return behavior, cfg
}

func hasBehaviorOnCamera(ctx context.Context, svc *spatial.Service, orgID uuid.UUID, cameraID, behavior string) bool {
	if svc == nil || behavior == "" {
		return false
	}
	zones, _ := svc.ListZones(ctx, orgID, nil)
	for _, z := range zones {
		if cameraID != "" && z.CameraID != nil && z.CameraID.String() != cameraID {
			continue
		}
		b, _ := parseBehaviorConfig(z.BehaviorConfig)
		if b == behavior {
			return true
		}
	}
	return false
}

func zoneBehaviorForName(ctx context.Context, svc *spatial.Service, orgID uuid.UUID, name string) string {
	zones, _ := svc.ListZones(ctx, orgID, nil)
	for _, z := range zones {
		if z.Name == name {
			b, _ := parseBehaviorConfig(z.BehaviorConfig)
			return b
		}
	}
	lines, _ := svc.ListLines(ctx, orgID, nil)
	for _, l := range lines {
		if l.Name == name {
			b, _ := parseBehaviorConfig(l.BehaviorConfig)
			return b
		}
	}
	return ""
}

func zoneClassFilter(ctx context.Context, svc *spatial.Service, orgID uuid.UUID, name string) string {
	zones, _ := svc.ListZones(ctx, orgID, nil)
	for _, z := range zones {
		if z.Name == name {
			_, cfg := parseBehaviorConfig(z.BehaviorConfig)
			if cfg != nil {
				if cf, ok := cfg["class_filter"].(string); ok {
					return cf
				}
			}
		}
	}
	return ""
}

func behaviorEmits(zb *capabilities.ZoneBehaviorsFile, behaviorID, eventType string) bool {
	if zb == nil {
		return true
	}
	for _, b := range zb.Behaviors {
		if b.ID != behaviorID {
			continue
		}
		for _, e := range b.Emits {
			if e == eventType {
				return true
			}
		}
		return false
	}
	return true
}

func zoneHasCalibratedEdge(ctx context.Context, svc *spatial.Service, orgID uuid.UUID, zoneName string) bool {
	zones, _ := svc.ListZones(ctx, orgID, nil)
	for _, z := range zones {
		if z.Name != zoneName {
			continue
		}
		var poly []map[string]interface{}
		if json.Unmarshal(z.Polygon, &poly) != nil {
			return false
		}
		for _, p := range poly {
			if d, ok := p["distance_to_next_m"].(float64); ok && d > 0 {
				return true
			}
		}
		return false
	}
	return false
}
