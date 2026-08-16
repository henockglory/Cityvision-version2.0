// Command seed-demo-rules creates the reference demo rules from existing catalog
// templates, bound to the demo cameras/zones/lines that are already drawn in the database.
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
//	#   DEMO_RULES_ONLY=a,b      only upsert rules whose names contain these substrings
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

// evidenceKind selects the evidence pack (must match product archetypes).
// road: scene+subject+plate+clip6 | geometry: scene+subject+clip6 | cabin: scene+subject clip0
type evidenceKind string

const (
	evidenceNone     evidenceKind = ""
	evidenceRoad     evidenceKind = "road"
	evidenceGeometry evidenceKind = "geometry"
	evidenceCabin    evidenceKind = "cabin"
)

type ruleSpec struct {
	name        string
	description string
	templateID  string
	severity    string
	cameraMatch string // substring matched against camera name (case-insensitive)
	zoneName    string // bindings.zone_name (orchestrator scoping)
	zoneName2   string // optional second zone (synergy)
	lineName    string // bindings.line_name
	classFilter string // bindings.class_filter
	speedKmh    float64
	eventTypes  []string
	withEmail   bool
	withClip    bool // add record action when evidence uses a clip
	observation bool
	obsKind     string
	evidence    evidenceKind
	clipSeconds float64 // 0 = kind default (6s road/geometry, 0s cabin)
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
			evidence:    evidenceRoad,
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
			evidence:    evidenceNone,
		},
		{
			name:        "Démo · Excès de vitesse",
			description: "Véhicule dépassant la limite dans Zone_distance_parcourue2 (calibration live).",
			templateID:  "tpl-speeding-premium",
			severity:    "high",
			cameraMatch: "ligne continue",
			zoneName:    "Zone_distance_parcourue2",
			classFilter: "any",
			speedKmh:    1,
			eventTypes:  []string{"speeding"},
			withEmail:   true,
			withClip:    true,
			evidence:    evidenceRoad,
		},
		{
			name:        "Démo · Téléphone au volant",
			description: "Usage du téléphone au volant — Frigate détecte le véhicule dans Zone_bbox ; Gemini VLM juge (FRIGATE_VLM_BRIDGE).",
			templateID:  "tpl-phone-driving",
			severity:    "medium",
			cameraMatch: "ceinture",
			zoneName:    "Zone_bbox",
			classFilter: "car",
			eventTypes:  []string{"phone_use_violation"},
			withEmail:   true,
			withClip:    false,
			evidence:    evidenceCabin,
		},
		{
			name:        "Démo · Non-port ceinture",
			description: "Absence de ceinture — Frigate détecte le véhicule dans Zone_bbox2 ; Gemini VLM juge (FRIGATE_VLM_BRIDGE).",
			templateID:  "tpl-seatbelt",
			severity:    "medium",
			cameraMatch: "ceinture",
			zoneName:    "Zone_bbox2",
			classFilter: "car",
			eventTypes:  []string{"seatbelt_violation"},
			withEmail:   true,
			withClip:    false,
			evidence:    evidenceCabin,
		},
		{
			name:        "Démo · Lecture plaque",
			description: "Lecture de plaque sur Démo — Okapi / zone lecture_plaque (OCR + preuves scène/cible/plaque).",
			templateID:  "tpl-plate-detected",
			severity:    "medium",
			cameraMatch: "okapi",
			zoneName:    "lecture_plaque",
			classFilter: "car",
			eventTypes:  []string{"plate_detected"},
			withEmail:   true,
			withClip:    true,
			evidence:    evidenceRoad,
			clipSeconds: 10,
		},
		{
			name:        "Démo · Intrusion",
			description: "Intrusion personne dans Zone_surveillee (perimeter_breach) sur Démo — In_Out.",
			templateID:  "tpl-intrusion",
			severity:    "high",
			cameraMatch: "in_out",
			zoneName:    "Zone_surveillee",
			classFilter: "person",
			eventTypes:  []string{"perimeter_breach"},
			withEmail:   true,
			withClip:    true,
			evidence:    evidenceGeometry,
		},
		{
			name:        "Démo · Non-port ceinture Zoom",
			description: "Absence de ceinture — Démo — Zoom_Entree_Hologram / Zone_seatbelt (pack cabin sans plaque).",
			templateID:  "tpl-seatbelt",
			severity:    "medium",
			cameraMatch: "zoom_entree",
			zoneName:    "Zone_seatbelt",
			classFilter: "car",
			eventTypes:  []string{"seatbelt_violation"},
			withEmail:   true,
			withClip:    false,
			evidence:    evidenceCabin,
		},
		{
			name:        "Démo · Sens interdit",
			description: "Sens interdit — entrée autorisée P1-P2 / sortie P3-P4 sur Zone_sens_interdit (Démo — Entree_Hologram).",
			templateID:  "tpl-wrong-way",
			severity:    "high",
			cameraMatch: "entree_hologram",
			zoneName:    "Zone_sens_interdit",
			classFilter: "car",
			eventTypes:  []string{"wrong_way"},
			withEmail:   true,
			withClip:    true,
			evidence:    evidenceGeometry,
		},
	}
}

func main() {
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		log.Fatal("DATABASE_URL is required")
	}
	enabled := os.Getenv("DEMO_RULES_ENABLED") != "0"
	onlyFilter := parseOnlyFilter(os.Getenv("DEMO_RULES_ONLY"))

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
		if !ruleAllowed(spec.name, onlyFilter) {
			continue
		}
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

func parseOnlyFilter(raw string) []string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil
	}
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(strings.ToLower(p))
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

func ruleAllowed(name string, only []string) bool {
	if len(only) == 0 {
		return true
	}
	n := strings.ToLower(name)
	for _, o := range only {
		if strings.Contains(n, o) {
			return true
		}
	}
	return false
}

func resolveOrg(ctx context.Context, pool *pgxpool.Pool) (uuid.UUID, error) {
	if v := os.Getenv("ORG_ID"); v != "" {
		return uuid.Parse(v)
	}
	var id uuid.UUID
	err := pool.QueryRow(ctx, `
		SELECT org_id FROM cameras
		WHERE metadata->>'demo' = 'true' OR metadata->>'virtual' = 'true'
		GROUP BY org_id ORDER BY COUNT(*) DESC LIMIT 1`).Scan(&id)
	if err == nil {
		return id, nil
	}
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
	bestID := uuid.Nil
	bestLen := int(^uint(0) >> 1)
	for _, c := range cams {
		n := strings.ToLower(c.name)
		if !strings.Contains(n, s) {
			continue
		}
		if len(n) < bestLen {
			bestLen = len(n)
			bestID = c.id
		}
	}
	return bestID
}

func buildDefinition(spec ruleSpec, camID uuid.UUID) map[string]interface{} {
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

	// Scope to zone/line when present so multi-camera orgs don't cross-fire.
	if spec.zoneName != "" && !spec.observation {
		condition = map[string]interface{}{
			"op": "AND",
			"children": []map[string]interface{}{
				condition,
				{"op": "eq", "field": "zone_id", "value": spec.zoneName},
			},
		}
	}
	if spec.classFilter != "" && spec.classFilter != "any" && !spec.observation {
		condition = map[string]interface{}{
			"op": "AND",
			"children": []map[string]interface{}{
				condition,
				{"op": "matches_class", "field": "class_name", "value": spec.classFilter},
			},
		}
	}

	bindings := map[string]interface{}{
		"template_id": spec.templateID,
		"camera_id":   camID.String(),
		"demo":        true,
		"origin":      "user",
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
		"dedup_key_fields": []string{"event_id"},
	}
	if spec.observation || spec.evidence == evidenceNone {
		def["evidence"] = map[string]interface{}{
			"enabled": false, "clip_seconds": 0, "images": []interface{}{}, "draw_bbox": false,
		}
	} else {
		def["evidence"] = evidencePolicy(spec.evidence, spec.clipSeconds)
	}
	return def
}

func evidencePolicy(kind evidenceKind, clipSec float64) map[string]interface{} {
	scene := map[string]interface{}{"role": "scene", "label": "Vue d'ensemble", "crop": "full"}
	subject := map[string]interface{}{"role": "subject", "label": "Cible détectée", "crop": "bbox", "padding_pct": 12, "zoom": 1.0}
	plate := map[string]interface{}{"role": "plate", "label": "Plaque", "crop": "plate_rear", "padding_pct": 6, "zoom": 1.8}

	switch kind {
	case evidenceCabin:
		return map[string]interface{}{
			"enabled":      true,
			"clip_seconds": 0,
			"draw_bbox":    true,
			"images":       []map[string]interface{}{scene, subject},
			"fail_closed":  []string{"scene", "subject"},
		}
	case evidenceGeometry:
		if clipSec <= 0 {
			clipSec = 6
		}
		return map[string]interface{}{
			"enabled":      true,
			"clip_seconds": clipSec,
			"draw_bbox":    true,
			"images":       []map[string]interface{}{scene, subject},
			"fail_closed":  []string{"subject"},
		}
	default: // road / plate / speeding / red light
		if clipSec <= 0 {
			clipSec = 6
		}
		return map[string]interface{}{
			"enabled":      true,
			"clip_seconds": clipSec,
			"draw_bbox":    true,
			"images":       []map[string]interface{}{scene, subject, plate},
			"fail_closed":  []string{"subject", "plate"},
		}
	}
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
