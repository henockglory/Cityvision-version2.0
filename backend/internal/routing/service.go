package routing

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/citevision/citevision-v2/backend/internal/alerts"
	"github.com/citevision/citevision-v2/backend/internal/notify"
	"github.com/citevision/citevision-v2/backend/internal/org"
)

var ErrNotFound = errors.New("routing rule not found")

type Rule struct {
	ID        uuid.UUID       `json:"id"`
	OrgID     uuid.UUID       `json:"org_id"`
	Name      string          `json:"name"`
	Enabled   bool            `json:"enabled"`
	Priority  int             `json:"priority"`
	Match     json.RawMessage `json:"match"`
	Channels  json.RawMessage `json:"channels"`
	CreatedAt time.Time       `json:"created_at"`
	UpdatedAt time.Time       `json:"updated_at"`
}

type Service struct {
	pool *pgxpool.Pool
}

func NewService(pool *pgxpool.Pool) *Service {
	return &Service{pool: pool}
}

func (s *Service) List(ctx context.Context, orgID uuid.UUID) ([]Rule, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, org_id, name, enabled, priority, match, channels, created_at, updated_at
		FROM alert_routing_rules WHERE org_id = $1 ORDER BY priority ASC, created_at ASC`, orgID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Rule
	for rows.Next() {
		var r Rule
		if err := rows.Scan(&r.ID, &r.OrgID, &r.Name, &r.Enabled, &r.Priority, &r.Match, &r.Channels, &r.CreatedAt, &r.UpdatedAt); err != nil {
			return nil, err
		}
		out = append(out, r)
	}
	return out, rows.Err()
}

func (s *Service) Create(ctx context.Context, orgID uuid.UUID, name string, priority int, match, channels json.RawMessage) (*Rule, error) {
	if match == nil {
		match = json.RawMessage(`{}`)
	}
	if channels == nil {
		channels = json.RawMessage(`{}`)
	}
	var r Rule
	err := s.pool.QueryRow(ctx, `
		INSERT INTO alert_routing_rules (org_id, name, priority, match, channels)
		VALUES ($1,$2,$3,$4,$5)
		RETURNING id, org_id, name, enabled, priority, match, channels, created_at, updated_at`,
		orgID, name, priority, match, channels,
	).Scan(&r.ID, &r.OrgID, &r.Name, &r.Enabled, &r.Priority, &r.Match, &r.Channels, &r.CreatedAt, &r.UpdatedAt)
	return &r, err
}

func (s *Service) Update(ctx context.Context, orgID, id uuid.UUID, name *string, enabled *bool, priority *int, match, channels json.RawMessage) (*Rule, error) {
	var r Rule
	err := s.pool.QueryRow(ctx, `
		UPDATE alert_routing_rules SET
			name = COALESCE($3, name),
			enabled = COALESCE($4, enabled),
			priority = COALESCE($5, priority),
			match = COALESCE($6, match),
			channels = COALESCE($7, channels),
			updated_at = NOW()
		WHERE id = $1 AND org_id = $2
		RETURNING id, org_id, name, enabled, priority, match, channels, created_at, updated_at`,
		id, orgID, name, enabled, priority, match, channels,
	).Scan(&r.ID, &r.OrgID, &r.Name, &r.Enabled, &r.Priority, &r.Match, &r.Channels, &r.CreatedAt, &r.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	return &r, err
}

func (s *Service) Delete(ctx context.Context, orgID, id uuid.UUID) error {
	tag, err := s.pool.Exec(ctx, `DELETE FROM alert_routing_rules WHERE id = $1 AND org_id = $2`, id, orgID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (s *Service) DispatchAuto(ctx context.Context, orgSvc *org.Service, alertsSvc *alerts.Service, orgID uuid.UUID, alertID uuid.UUID) {
	rules, err := s.List(ctx, orgID)
	if err != nil || len(rules) == 0 {
		return
	}
	enriched, err := alertsSvc.GetByID(ctx, orgID, alertID)
	if err != nil {
		return
	}
	o, err := orgSvc.Get(ctx, orgID)
	if err != nil {
		return
	}
	smtpCfg := notify.ParseSMTP(o.SMTPConfig)

	fields := extractMatchFields(enriched)
	for _, rule := range rules {
		if !rule.Enabled {
			continue
		}
		if !matchesRule(rule, fields) {
			continue
		}
		ch := parseChannels(rule.Channels)
		logEntry := map[string]interface{}{
			"timestamp":        time.Now().UTC().Format(time.RFC3339),
			"source":           "auto_route",
			"routing_rule_id":  rule.ID.String(),
			"routing_rule_name": rule.Name,
			"channels":         []string{},
		}
		var evSnap map[string]interface{}
		_ = json.Unmarshal(enriched.EvidenceSnapshot, &evSnap)

		for _, email := range ch.Emails {
			if email == "" {
				continue
			}
			msg := buildEmailBody(enriched, evSnap)
			_ = notify.SendAlert(smtpCfg, email, "CitéVision — "+enriched.Title, msg)
			logEntry["channels"] = append(logEntry["channels"].([]string), "email")
			if logEntry["email"] == nil {
				logEntry["email"] = email
			}
		}
		if ch.WebhookURL != "" {
			payload := map[string]interface{}{
				"org_id":            orgID.String(),
				"alert_id":          alertID.String(),
				"title":             enriched.Title,
				"severity":          enriched.Severity,
				"timestamp":         time.Now().UTC().Format(time.RFC3339),
				"evidence_snapshot": evSnap,
				"camera_id":         enriched.CameraID,
				"rule_name":         enriched.RuleName,
				"plate_number":      fields["plate_number"],
				"face_label":        fields["face_label"],
				"event_type":        fields["event_type"],
				"routing_rule":      rule.Name,
			}
			if ch.WebhookPreset != "" {
				payload["integration_preset"] = ch.WebhookPreset
			}
			if err := PostWebhookPreset(ch.WebhookURL, ch.WebhookPreset, payload); err == nil {
				logEntry["channels"] = append(logEntry["channels"].([]string), "webhook")
				logEntry["webhook_url"] = ch.WebhookURL
				if ch.WebhookPreset != "" {
					logEntry["webhook_preset"] = ch.WebhookPreset
				}
			} else {
				logEntry["webhook_error"] = err.Error()
			}
		}
		if len(logEntry["channels"].([]string)) > 0 {
			_ = alertsSvc.AppendForwardLog(ctx, orgID, alertID, logEntry)
		}
	}
}

type channelConfig struct {
	Emails        []string
	WebhookURL    string
	WebhookPreset string
}

func parseChannels(raw json.RawMessage) channelConfig {
	var m map[string]interface{}
	_ = json.Unmarshal(raw, &m)
	out := channelConfig{}
	if v, ok := m["emails"].([]interface{}); ok {
		for _, e := range v {
			if s, ok := e.(string); ok && s != "" {
				out.Emails = append(out.Emails, s)
			}
		}
	}
	if v, ok := m["email"].(string); ok && v != "" {
		out.Emails = append(out.Emails, v)
	}
	if v, ok := m["webhook_url"].(string); ok {
		out.WebhookURL = v
	}
	if v, ok := m["webhook_preset"].(string); ok {
		out.WebhookPreset = v
	}
	return out
}

func extractMatchFields(a *alerts.EnrichedAlert) map[string]string {
	out := map[string]string{
		"severity": strings.ToLower(a.Severity),
	}
	var meta map[string]interface{}
	_ = json.Unmarshal(a.Metadata, &meta)
	var ev map[string]interface{}
	_ = json.Unmarshal(a.EvidenceSnapshot, &ev)
	for _, src := range []map[string]interface{}{meta, ev} {
		for _, k := range []string{"plate_number", "face_label", "event_type", "class_name"} {
			if v, ok := src[k].(string); ok && v != "" && out[k] == "" {
				out[k] = strings.TrimSpace(v)
			}
		}
	}
	if payload, ok := meta["payload"].(map[string]interface{}); ok {
		for _, k := range []string{"plate_number", "face_label", "event_type"} {
			if v, ok := payload[k].(string); ok && v != "" && out[k] == "" {
				out[k] = strings.TrimSpace(v)
			}
		}
	}
	return out
}

func matchesRule(rule Rule, fields map[string]string) bool {
	return MatchRule(rule, fields)
}

// MatchRule evaluates a routing rule against alert fields (exported for tests/handlers).
func MatchRule(rule Rule, fields map[string]string) bool {
	var m map[string]interface{}
	if err := json.Unmarshal(rule.Match, &m); err != nil {
		return false
	}
	matchType, _ := m["type"].(string)
	matchType = strings.ToLower(strings.TrimSpace(matchType))
	wantVal, _ := m["value"].(string)
	wantVal = strings.TrimSpace(wantVal)

	switch matchType {
	case "", "any", "*":
		return true
	case "plate":
		return wantVal != "" && strings.EqualFold(fields["plate_number"], wantVal)
	case "face":
		return wantVal != "" && strings.EqualFold(fields["face_label"], wantVal)
	case "event_type":
		return wantVal != "" && strings.EqualFold(fields["event_type"], wantVal)
	case "severity":
		return wantVal != "" && strings.EqualFold(fields["severity"], wantVal)
	default:
		return false
	}
}

func buildEmailBody(a *alerts.EnrichedAlert, evSnap map[string]interface{}) string {
	var b strings.Builder
	fmt.Fprintf(&b, "Alerte : %s\n", a.Title)
	if a.RuleName != nil {
		fmt.Fprintf(&b, "Règle : %s\n", *a.RuleName)
	}
	if a.CameraID != "" {
		fmt.Fprintf(&b, "Caméra : %s\n", a.CameraID)
	}
	if evSnap != nil {
		if p, ok := evSnap["plate_number"].(string); ok && p != "" {
			fmt.Fprintf(&b, "Plaque : %s\n", p)
		}
		if f, ok := evSnap["face_label"].(string); ok && f != "" {
			fmt.Fprintf(&b, "Visage : %s\n", f)
		}
	}
	b.WriteString("\nLiens preuves :\n")
	if pkg, ok := evSnap["package"].(map[string]interface{}); ok {
		if clip, ok := pkg["clip"].(map[string]interface{}); ok {
			if u, ok := clip["url"].(string); ok && u != "" {
				fmt.Fprintf(&b, "- Clip : %s\n", u)
			}
		}
	}
	return b.String()
}
