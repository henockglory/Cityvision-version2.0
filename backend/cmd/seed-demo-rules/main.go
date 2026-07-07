// Command seed-demo-rules creates the 5 reference demo rules (red light, vehicle
// counting, speeding, phone use, seatbelt) from existing catalog templates, bound
// to the demo cameras/zones/lines that are already drawn in the database.
//
// It is idempotent: a rule is matched by its (org, name) and updated in place if it
// already exists, otherwise inserted. Rules are stamped bindings.origin="user" so
// they survive the demo "reset" (which only purges non-user rules).
//
// Usage:
//
//	DATABASE_URL=postgres://... go run ./cmd/seed-demo-rules
//	# optional:
//	#   ORG_ID=<uuid>            pin the org (else: org owning demo cameras)
//	#   DEMO_RULES_ENABLED=0     create disabled (default: 1 = enabled for testing)
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type ruleSpec struct {
	name        string
	description string
	templateID  string
	severity    string
	cameraMatch string   // substring matched against camera name (case-insensitive)
	zoneName    string   // bindings.zone_name (orchestrator scoping)
	zoneName2   string   // optional second zone (synergy)
	lineName    string   // bindings.line_name
	classFilter string   // bindings.class_filter
	speedKmh    float64  // bindings.speed_kmh (0 = none)
	eventTypes  []string // condition matches any of these event_type values
	withEmail   bool     // add notify action (falls back to org default_email_to)
	withClip    bool     // add record action + evidence policy
	observation bool     // observation_mode: counter only, no alert/evidence
	obsKind     string   // observation_kind binding
}

func demoRuleSpecs() []ruleSpec {
	return []ruleSpec{
		{
			name:        "Démo · Feu rouge",
			description: "Véhicule franchissant au feu rouge (synergie Zone_des_feux + Zone_Observation).",
			templateID:  "tpl-red-light",
			severity:    "high",
			cameraMatch: "feux",
			zoneName:    "Zone_Observation",
			zoneName2:   "Zone_des_feux",
			classFilter: "any",
			eventTypes:  []string{"red_light_violation"},
			withEmail:   true,
			withClip:    true,
		},
		{
			name:        "Démo · Comptage véhicules",
			description: "Comptage des véhicules franchissant Ligne_count (compteur visible).",
			templateID:  "tpl-line-cross-bidir",
			severity:    "low",
			cameraMatch: "décompte",
			lineName:    "Ligne_count",
			classFilter: "car",
			eventTypes:  []string{"line_cross"},
			withEmail:   false,
			withClip:    false,
			observation: true,
			obsKind:     "line_cross",
		},
		{
			name:        "Démo · Excès de vitesse",
			description: "Véhicule dépassant 12 km/h dans Zone_distance_parcourue (calibration 12 m).",
			templateID:  "tpl-speeding-premium",
			severity:    "high",
			cameraMatch: "ligne continue",
			zoneName:    "Zone_distance_parcourue",
			classFilter: "any",
			speedKmh:    8,
			eventTypes:  []string{"speeding"},
			withEmail:   true,
			withClip:    true,
		},
		{
			name:        "Démo · Téléphone au volant",
			description: "Usage du téléphone au volant détecté dans Zone_bbox (modèle ONNX + repli heuristique).",
			templateID:  "tpl-phone-driving",
			severity:    "medium",
			cameraMatch: "ceinture",
			zoneName:    "Zone_bbox",
			classFilter: "car",
			// [F.58]/[P.134] Canonical ONNX event only; legacy heuristic emits phone_driving when model absent.
			eventTypes: []string{"phone_use_violation"},
			withEmail:  true,
			withClip:   true,
		},
		{
			name:        "Démo · Non-port ceinture",
			description: "Absence de ceinture détectée dans Zone_bbox (modèle ONNX + repli heuristique).",
			templateID:  "tpl-seatbelt",
			severity:    "medium",
			cameraMatch: "ceinture",
			zoneName:    "Zone_bbox2", // seatbelt behavior runs on Zone_bbox2 ([B.20]/[C.32])
			classFilter: "car",
			eventTypes:  []string{"seatbelt_violation"},
			withEmail:   true,
			withClip:    true,
		},
	}
}

func main() {
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		log.Fatal("DATABASE_URL is required")
	}
	enabled := os.Getenv("DEMO_RULES_ENABLED") != "0"

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	pool, err := pgxpool.New(ctx, dbURL)
	if err != nil {
		log.Fatalf("connect db: %v", err)
	}
	defer pool.Close()

	orgID, err := resolveOrg(ctx, pool)
	if err != nil {
		log.Fatalf("resolve org: %v", err)
	}
	log.Printf("org: %s", orgID)

	cameras, err := loadCameras(ctx, pool, orgID)
	if err != nil {
		log.Fatalf("load cameras: %v", err)
	}

	var created, updated, skipped int
	for _, spec := range demoRuleSpecs() {
		camID := matchCamera(cameras, spec.cameraMatch)
		if camID == uuid.Nil {
			log.Printf("SKIP %q: no camera matching %q", spec.name, spec.cameraMatch)
			skipped++
			continue
		}
		def := buildDefinition(spec, camID)
		defJSON, _ := json.Marshal(def)

		action, err := upsertRule(ctx, pool, orgID, spec, defJSON, enabled)
		if err != nil {
			log.Printf("ERROR %q: %v", spec.name, err)
			skipped++
			continue
		}
		switch action {
		case "created":
			created++
		case "updated":
			updated++
		}
		log.Printf("%-8s %q (cam %s, enabled=%v)", action, spec.name, camID, enabled)
	}

	log.Printf("done: %d created, %d updated, %d skipped", created, updated, skipped)
}

func resolveOrg(ctx context.Context, pool *pgxpool.Pool) (uuid.UUID, error) {
	if v := os.Getenv("ORG_ID"); v != "" {
		return uuid.Parse(v)
	}
	// Prefer the org that owns demo cameras (metadata.demo = true).
	var id uuid.UUID
	err := pool.QueryRow(ctx, `
		SELECT org_id FROM cameras
		WHERE metadata->>'demo' = 'true' OR metadata->>'virtual' = 'true'
		GROUP BY org_id ORDER BY COUNT(*) DESC LIMIT 1`).Scan(&id)
	if err == nil {
		return id, nil
	}
	// Fallback: the only / first organization.
	if err := pool.QueryRow(ctx, `SELECT id FROM organizations ORDER BY created_at ASC LIMIT 1`).Scan(&id); err != nil {
		return uuid.Nil, fmt.Errorf("no org found: %w", err)
	}
	return id, nil
}

type camInfo struct {
	id   uuid.UUID
	name string
}

func loadCameras(ctx context.Context, pool *pgxpool.Pool, orgID uuid.UUID) ([]camInfo, error) {
	rows, err := pool.Query(ctx, `SELECT id, name FROM cameras WHERE org_id = $1`, orgID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []camInfo
	for rows.Next() {
		var c camInfo
		if err := rows.Scan(&c.id, &c.name); err != nil {
			return nil, err
		}
		out = append(out, c)
	}
	return out, rows.Err()
}

func matchCamera(cams []camInfo, substr string) uuid.UUID {
	s := strings.ToLower(substr)
	for _, c := range cams {
		if strings.Contains(strings.ToLower(c.name), s) {
			return c.id
		}
	}
	return uuid.Nil
}

// buildDefinition mirrors the frontend ruleDefinitionBuilder output so seeded rules
// are indistinguishable from UI-created ones.
func buildDefinition(spec ruleSpec, camID uuid.UUID) map[string]interface{} {
	// Condition: match any of the event types (OR), kept minimal so detections fire.
	var condition map[string]interface{}
	if len(spec.eventTypes) == 1 {
		condition = map[string]interface{}{"op": "eq", "field": "event_type", "value": spec.eventTypes[0]}
	} else {
		children := make([]map[string]interface{}, 0, len(spec.eventTypes))
		for _, et := range spec.eventTypes {
			children = append(children, map[string]interface{}{"op": "eq", "field": "event_type", "value": et})
		}
		condition = map[string]interface{}{"op": "OR", "children": children}
	}

	bindings := map[string]interface{}{
		"template_id": spec.templateID,
		"camera_id":   camID.String(),
		"demo":        true,
		"origin":      "user", // survive demo reset
	}
	if spec.zoneName != "" {
		bindings["zone_name"] = spec.zoneName
	}
	if spec.zoneName2 != "" {
		bindings["zone_name_2"] = spec.zoneName2
	}
	if spec.lineName != "" {
		bindings["line_name"] = spec.lineName
	}
	if spec.classFilter != "" {
		bindings["class_filter"] = spec.classFilter
	}
	if spec.speedKmh > 0 {
		bindings["speed_kmh"] = spec.speedKmh
	}
	if spec.observation {
		bindings["observation_mode"] = true
		if spec.obsKind != "" {
			bindings["observation_kind"] = spec.obsKind
		}
		bindings["observation_label_fr"] = spec.name
		bindings["observation_label_en"] = spec.name
	}

	var actions []map[string]interface{}
	if spec.observation {
		actions = []map[string]interface{}{
			{"type": "counter", "config": map[string]interface{}{"delta": 1}},
		}
	} else {
		actions = []map[string]interface{}{
			{"type": "alert", "config": map[string]interface{}{"severity": spec.severity}},
		}
	}
	if !spec.observation && spec.withClip {
		actions = append(actions, map[string]interface{}{"type": "record", "config": map[string]interface{}{}})
	}
	if !spec.observation && spec.withEmail {
		to := os.Getenv("ALERT_EMAIL_TO")
		if to == "" {
			to = os.Getenv("ADMIN_EMAIL")
		}
		if to == "" {
			to = "glory.henock@hologram.cd"
		}
		actions = append(actions, map[string]interface{}{
			"type": "notify",
			"config": map[string]interface{}{
				"channel":  "email",
				"severity": spec.severity,
				"to":       to,
			},
		})
	}

	def := map[string]interface{}{
		"camera_id":        camID.String(),
		"condition":        condition,
		"bindings":         bindings,
		"actions":          actions,
		"dedup_key_fields": []string{"camera_id", "event_id"},
	}
	if spec.withClip && !spec.observation {
		def["evidence"] = map[string]interface{}{
			"enabled":      true,
			"clip_seconds": 6,
			"draw_bbox":    true,
			"images": []map[string]interface{}{
				{"role": "scene", "label": "Vue d'ensemble", "crop": "full"},
				{"role": "subject", "label": "Cible détectée", "crop": "full", "padding_pct": 8, "zoom": 1.0},
				{"role": "plate", "label": "Plaque arrière", "crop": "plate_rear", "padding_pct": 6, "zoom": 1.8},
			},
		}
	}
	if spec.observation {
		def["evidence"] = map[string]interface{}{
			"enabled": false, "clip_seconds": 0, "images": []interface{}{}, "draw_bbox": false,
		}
	}
	return def
}

func upsertRule(ctx context.Context, pool *pgxpool.Pool, orgID uuid.UUID, spec ruleSpec, defJSON []byte, enabled bool) (string, error) {
	var existingID uuid.UUID
	err := pool.QueryRow(ctx, `SELECT id FROM rules WHERE org_id = $1 AND name = $2 LIMIT 1`, orgID, spec.name).Scan(&existingID)
	if err == nil {
		_, uerr := pool.Exec(ctx, `
			UPDATE rules SET definition = $3, description = $4, is_enabled = $5, updated_at = NOW()
			WHERE id = $1 AND org_id = $2`,
			existingID, orgID, defJSON, spec.description, enabled)
		if uerr != nil {
			return "", uerr
		}
		return "updated", nil
	}
	if err != pgx.ErrNoRows {
		return "", err
	}
	_, ierr := pool.Exec(ctx, `
		INSERT INTO rules (org_id, name, description, definition, is_enabled, priority)
		VALUES ($1,$2,$3,$4,$5,$6)`,
		orgID, spec.name, spec.description, defJSON, enabled, 100)
	if ierr != nil {
		return "", ierr
	}
	return "created", nil
}
