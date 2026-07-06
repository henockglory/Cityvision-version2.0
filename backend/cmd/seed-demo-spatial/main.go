// Command seed-demo-spatial applies behavior_config to existing demo zones/lines
// without modifying polygons. Idempotent: matched by (camera, zone/line name).
//
// Usage: DATABASE_URL=postgres://... go run ./cmd/seed-demo-spatial
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
	"github.com/jackc/pgx/v5/pgxpool"
)

type zonePatch struct {
	cameraMatch string
	zoneName    string
	behavior    string
	config      map[string]interface{}
	optional    bool
}

type linePatch struct {
	cameraMatch string
	lineName    string
	active      bool
}

func patches() ([]zonePatch, []linePatch) {
	zones := []zonePatch{
		{
			cameraMatch: "feux",
			zoneName:    "Zone_des_feux",
			behavior:    "traffic_light_color",
			config:      map[string]interface{}{"stable_frames": 1},
		},
		{
			cameraMatch: "feux",
			zoneName:    "Zone_Observation",
			behavior:    "red_light_observation",
			// Lower motion threshold + any vehicle class for demo video pacing.
			config: map[string]interface{}{"class_filter": "any", "min_speed_px": 0.1},
		},
		{
			cameraMatch: "ligne continue",
			zoneName:    "Zone_distance_parcourue",
			behavior:    "speed_measurement",
			config: map[string]interface{}{
				"distance_m":         8.0,
				"edge_distances_m":   []interface{}{8.0, 2.0, 8.0, 2.0},
				"speed_limit_kmh":    8,
				"cooldown_sec":       2.0,
				"spatial_dedup_sec":  2.0,
				"class_filter":       "any",
			},
		},
		// [P.130] The user drew TWO cabin zones (Zone_bbox + Zone_bbox2), one per
		// violation, not a single driver_cabin zone. Match the real drawing.
		{
			cameraMatch: "ceinture",
			zoneName:    "Zone_bbox",
			behavior:    "phone_use",
			config:      map[string]interface{}{"confidence": 0.35},
		},
		{
			cameraMatch: "ceinture",
			zoneName:    "Zone_bbox2",
			behavior:    "seatbelt",
			config:      map[string]interface{}{"confidence": 0.35},
		},
	}
	lines := []linePatch{
		{cameraMatch: "décompte", lineName: "Ligne_count", active: true},
	}
	// Optional ANPR zones — skipped if not drawn in DB.
	zones = append(zones,
		zonePatch{
			cameraMatch: "feux",
			zoneName:    "Zone_plaque",
			behavior:    "plate_ocr",
			config:      map[string]interface{}{"class_filter": "any"},
			optional:    true,
		},
		zonePatch{
			cameraMatch: "ligne continue",
			zoneName:    "Zone_plaque",
			behavior:    "plate_ocr",
			config:      map[string]interface{}{"class_filter": "any"},
			optional:    true,
		},
	)
	return zones, lines
}

func main() {
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		log.Fatal("DATABASE_URL is required")
	}
	if v := os.Getenv("SPEED_DISTANCE_M"); v != "" {
		// optional override for calibration
		var dist float64
		if _, err := fmt.Sscanf(v, "%f", &dist); err == nil && dist > 0 {
			z, l := patches()
			for i := range z {
				if z[i].zoneName == "Zone_distance_parcourue" {
					z[i].config["distance_m"] = dist
				}
			}
			_ = l
			run(dbURL, z, l)
			return
		}
	}
	z, l := patches()
	run(dbURL, z, l)
}

func run(dbURL string, zonePatches []zonePatch, linePatches []linePatch) {
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

	cams, err := loadCameras(ctx, pool, orgID)
	if err != nil {
		log.Fatalf("load cameras: %v", err)
	}

	var updated, missing int
	for _, p := range zonePatches {
		camID := matchCamera(cams, p.cameraMatch)
		if camID == uuid.Nil {
			log.Printf("MISSING camera matching %q for zone %q", p.cameraMatch, p.zoneName)
			missing++
			continue
		}
		cfg := map[string]interface{}{
			"behavior": p.behavior,
			"config":   p.config,
		}
		raw, _ := json.Marshal(cfg)
		tag, err := pool.Exec(ctx, `
			UPDATE zones SET behavior_config = $4, zone_kind = $5, updated_at = NOW()
			WHERE org_id = $1 AND camera_id = $2 AND name = $3`,
			orgID, camID, p.zoneName, raw, p.behavior)
		if err != nil {
			log.Printf("ERROR zone %q: %v", p.zoneName, err)
			missing++
			continue
		}
		if tag.RowsAffected() == 0 {
			if p.optional {
				log.Printf("SKIP optional zone %q on camera %s (not drawn)", p.zoneName, camID)
				continue
			}
			log.Printf("MISSING zone %q on camera %s", p.zoneName, camID)
			missing++
			continue
		}
		log.Printf("UPDATED zone %q -> behavior=%s", p.zoneName, p.behavior)
		updated++
	}

	for _, p := range linePatches {
		camID := matchCamera(cams, p.cameraMatch)
		if camID == uuid.Nil {
			log.Printf("MISSING camera matching %q for line %q", p.cameraMatch, p.lineName)
			missing++
			continue
		}
		tag, err := pool.Exec(ctx, `
			UPDATE lines SET is_active = $4, updated_at = NOW()
			WHERE org_id = $1 AND camera_id = $2 AND name = $3`,
			orgID, camID, p.lineName, p.active)
		if err != nil {
			log.Printf("ERROR line %q: %v", p.lineName, err)
			missing++
			continue
		}
		if tag.RowsAffected() == 0 {
			log.Printf("MISSING line %q on camera %s", p.lineName, camID)
			missing++
			continue
		}
		log.Printf("UPDATED line %q active=%v", p.lineName, p.active)
		updated++
	}

	log.Printf("done: %d updated, %d missing", updated, missing)
	if missing > 0 {
		os.Exit(1)
	}
}

func resolveOrg(ctx context.Context, pool *pgxpool.Pool) (uuid.UUID, error) {
	if v := os.Getenv("ORG_ID"); v != "" {
		return uuid.Parse(v)
	}
	var id uuid.UUID
	err := pool.QueryRow(ctx, `
		SELECT org_id FROM cameras
		WHERE metadata->>'demo' = 'true'
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
	for _, c := range cams {
		if strings.Contains(strings.ToLower(c.name), s) {
			return c.id
		}
	}
	return uuid.Nil
}
