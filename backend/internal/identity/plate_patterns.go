package identity

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// PlatePattern is a named plate composition filter for an org.
type PlatePattern struct {
	ID          uuid.UUID       `json:"id"`
	OrgID       uuid.UUID       `json:"org_id"`
	Name        string          `json:"name"`
	Mode        string          `json:"mode"` // standard | custom
	Composition json.RawMessage `json:"composition"`
	Regex       string          `json:"regex"`
	IsDefault   bool            `json:"is_default"`
	CreatedAt   string          `json:"created_at,omitempty"`
	UpdatedAt   string          `json:"updated_at,omitempty"`
}

// PlateSegment describes one block in a custom composition, e.g. charset A-Z × 2.
type PlateSegment struct {
	Charset string `json:"charset"` // "A-Z", "0-9", "A-Z0-9"
	Count   int    `json:"count"`
}

type PlatePatternCreateRequest struct {
	Name        string          `json:"name"`
	Mode        string          `json:"mode"`
	Composition json.RawMessage `json:"composition"`
	IsDefault   bool            `json:"is_default"`
}

type PlatePatternUpdateRequest struct {
	Name        *string          `json:"name,omitempty"`
	Mode        *string          `json:"mode,omitempty"`
	Composition *json.RawMessage `json:"composition,omitempty"`
	IsDefault   *bool            `json:"is_default,omitempty"`
}

var (
	ErrPatternNotFound = errors.New("plate pattern not found")
	ErrPatternInvalid  = errors.New("invalid plate pattern")
)

// CompilePlateComposition turns segments into an anchored regex after alnum normalize.
func CompilePlateComposition(composition json.RawMessage) (string, error) {
	var segs []PlateSegment
	if len(composition) == 0 || string(composition) == "null" {
		return "", fmt.Errorf("%w: empty composition", ErrPatternInvalid)
	}
	if err := json.Unmarshal(composition, &segs); err != nil {
		return "", fmt.Errorf("%w: %v", ErrPatternInvalid, err)
	}
	if len(segs) == 0 {
		return "", fmt.Errorf("%w: no segments", ErrPatternInvalid)
	}
	var b strings.Builder
	b.WriteString("^")
	total := 0
	for _, s := range segs {
		if s.Count < 1 || s.Count > 12 {
			return "", fmt.Errorf("%w: count out of range", ErrPatternInvalid)
		}
		total += s.Count
		if total > 32 {
			return "", fmt.Errorf("%w: plate too long", ErrPatternInvalid)
		}
		cls := charsetClass(s.Charset)
		if cls == "" {
			return "", fmt.Errorf("%w: unsupported charset %q", ErrPatternInvalid, s.Charset)
		}
		b.WriteString(fmt.Sprintf("%s{%d}", cls, s.Count))
	}
	b.WriteString("$")
	re := b.String()
	if _, err := regexp.Compile(re); err != nil {
		return "", fmt.Errorf("%w: %v", ErrPatternInvalid, err)
	}
	return re, nil
}

func charsetClass(cs string) string {
	switch strings.ToUpper(strings.TrimSpace(cs)) {
	case "A-Z", "AZ", "LETTERS":
		return "[A-Z]"
	case "0-9", "09", "DIGITS", "DIGIT":
		return "[0-9]"
	case "A-Z0-9", "0-9A-Z", "ALNUM":
		return "[A-Z0-9]"
	default:
		return ""
	}
}

func normalizePatternReq(req *PlatePatternCreateRequest) error {
	req.Name = strings.TrimSpace(req.Name)
	if req.Name == "" {
		return fmt.Errorf("%w: name required", ErrPatternInvalid)
	}
	mode := strings.ToLower(strings.TrimSpace(req.Mode))
	if mode == "" {
		mode = "custom"
	}
	if mode != "standard" && mode != "custom" {
		return fmt.Errorf("%w: mode must be standard|custom", ErrPatternInvalid)
	}
	req.Mode = mode
	if mode == "standard" {
		req.Composition = json.RawMessage(`[]`)
		return nil
	}
	_, err := CompilePlateComposition(req.Composition)
	return err
}

func (s *Service) ListPlatePatterns(ctx context.Context, orgID uuid.UUID) ([]PlatePattern, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, org_id, name, mode, composition, regex, is_default, created_at::text, updated_at::text
		FROM plate_patterns WHERE org_id = $1
		ORDER BY is_default DESC, name ASC`, orgID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []PlatePattern
	for rows.Next() {
		var p PlatePattern
		if err := rows.Scan(&p.ID, &p.OrgID, &p.Name, &p.Mode, &p.Composition, &p.Regex, &p.IsDefault, &p.CreatedAt, &p.UpdatedAt); err != nil {
			return nil, err
		}
		out = append(out, p)
	}
	return out, rows.Err()
}

func (s *Service) GetPlatePattern(ctx context.Context, orgID, id uuid.UUID) (*PlatePattern, error) {
	var p PlatePattern
	err := s.pool.QueryRow(ctx, `
		SELECT id, org_id, name, mode, composition, regex, is_default, created_at::text, updated_at::text
		FROM plate_patterns WHERE id = $1 AND org_id = $2`, id, orgID,
	).Scan(&p.ID, &p.OrgID, &p.Name, &p.Mode, &p.Composition, &p.Regex, &p.IsDefault, &p.CreatedAt, &p.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrPatternNotFound
	}
	return &p, err
}

func (s *Service) CreatePlatePattern(ctx context.Context, orgID uuid.UUID, req PlatePatternCreateRequest) (*PlatePattern, error) {
	if err := normalizePatternReq(&req); err != nil {
		return nil, err
	}
	regex := ""
	if req.Mode == "custom" {
		var err error
		regex, err = CompilePlateComposition(req.Composition)
		if err != nil {
			return nil, err
		}
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx)
	if req.IsDefault {
		if _, err := tx.Exec(ctx, `UPDATE plate_patterns SET is_default = FALSE WHERE org_id = $1`, orgID); err != nil {
			return nil, err
		}
	}
	var p PlatePattern
	err = tx.QueryRow(ctx, `
		INSERT INTO plate_patterns (org_id, name, mode, composition, regex, is_default)
		VALUES ($1,$2,$3,$4,$5,$6)
		RETURNING id, org_id, name, mode, composition, regex, is_default, created_at::text, updated_at::text`,
		orgID, req.Name, req.Mode, req.Composition, regex, req.IsDefault,
	).Scan(&p.ID, &p.OrgID, &p.Name, &p.Mode, &p.Composition, &p.Regex, &p.IsDefault, &p.CreatedAt, &p.UpdatedAt)
	if err != nil {
		return nil, err
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	return &p, nil
}

func (s *Service) UpdatePlatePattern(ctx context.Context, orgID, id uuid.UUID, req PlatePatternUpdateRequest) (*PlatePattern, error) {
	cur, err := s.GetPlatePattern(ctx, orgID, id)
	if err != nil {
		return nil, err
	}
	name := cur.Name
	mode := cur.Mode
	comp := cur.Composition
	isDef := cur.IsDefault
	if req.Name != nil {
		name = strings.TrimSpace(*req.Name)
		if name == "" {
			return nil, fmt.Errorf("%w: name required", ErrPatternInvalid)
		}
	}
	if req.Mode != nil {
		mode = strings.ToLower(strings.TrimSpace(*req.Mode))
		if mode != "standard" && mode != "custom" {
			return nil, fmt.Errorf("%w: mode", ErrPatternInvalid)
		}
	}
	if req.Composition != nil {
		comp = *req.Composition
	}
	if req.IsDefault != nil {
		isDef = *req.IsDefault
	}
	regex := ""
	if mode == "custom" {
		regex, err = CompilePlateComposition(comp)
		if err != nil {
			return nil, err
		}
	} else {
		comp = json.RawMessage(`[]`)
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx)
	if isDef {
		if _, err := tx.Exec(ctx, `UPDATE plate_patterns SET is_default = FALSE WHERE org_id = $1 AND id <> $2`, orgID, id); err != nil {
			return nil, err
		}
	}
	var p PlatePattern
	err = tx.QueryRow(ctx, `
		UPDATE plate_patterns
		SET name = $1, mode = $2, composition = $3, regex = $4, is_default = $5, updated_at = NOW()
		WHERE id = $6 AND org_id = $7
		RETURNING id, org_id, name, mode, composition, regex, is_default, created_at::text, updated_at::text`,
		name, mode, comp, regex, isDef, id, orgID,
	).Scan(&p.ID, &p.OrgID, &p.Name, &p.Mode, &p.Composition, &p.Regex, &p.IsDefault, &p.CreatedAt, &p.UpdatedAt)
	if err != nil {
		return nil, err
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	return &p, nil
}

func (s *Service) DeletePlatePattern(ctx context.Context, orgID, id uuid.UUID) error {
	tag, err := s.pool.Exec(ctx, `DELETE FROM plate_patterns WHERE id = $1 AND org_id = $2`, id, orgID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrPatternNotFound
	}
	return nil
}

// ExportPlatePatternsForAI returns patterns for AI ingest (id, name, mode, regex, is_default).
func (s *Service) ExportPlatePatternsForAI(ctx context.Context, orgID uuid.UUID) ([]map[string]interface{}, error) {
	list, err := s.ListPlatePatterns(ctx, orgID)
	if err != nil {
		return nil, err
	}
	out := make([]map[string]interface{}, 0, len(list))
	for _, p := range list {
		out = append(out, map[string]interface{}{
			"id":         p.ID.String(),
			"name":       p.Name,
			"mode":       p.Mode,
			"regex":      p.Regex,
			"is_default": p.IsDefault,
		})
	}
	return out, nil
}
