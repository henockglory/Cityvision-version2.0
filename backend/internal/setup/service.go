package setup

import (
	"context"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"unicode"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/citevision/citevision-v2/backend/internal/auth"
	"github.com/citevision/citevision-v2/backend/internal/models"
)

var (
	ErrAlreadyInitialized = errors.New("system already initialized")
	ErrInvalidSetup       = errors.New("invalid setup request")
)

var slugRe = regexp.MustCompile(`^[a-z0-9]+(?:-[a-z0-9]+)*$`)

type Service struct {
	pool *pgxpool.Pool
}

func NewService(pool *pgxpool.Pool) *Service {
	return &Service{pool: pool}
}

func (s *Service) Status(ctx context.Context) (models.SetupStatus, error) {
	initialized, err := s.isInitialized(ctx)
	if err != nil {
		return models.SetupStatus{}, err
	}
	return models.SetupStatus{Initialized: initialized}, nil
}

func (s *Service) Complete(ctx context.Context, req models.SetupCompleteRequest) (*models.SetupCompleteResponse, error) {
	req = normalizeRequest(req)
	if err := validateRequest(req); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidSetup, err)
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx)

	initialized, err := s.isInitializedTx(ctx, tx)
	if err != nil {
		return nil, err
	}
	if initialized {
		return nil, ErrAlreadyInitialized
	}

	var orgCount, userCount int
	if err := tx.QueryRow(ctx, `SELECT COUNT(*) FROM organizations`).Scan(&orgCount); err != nil {
		return nil, err
	}
	if err := tx.QueryRow(ctx, `SELECT COUNT(*) FROM users`).Scan(&userCount); err != nil {
		return nil, err
	}
	if orgCount > 0 || userCount > 0 {
		return nil, ErrAlreadyInitialized
	}

	hash, err := auth.HashPassword(req.AdminPassword)
	if err != nil {
		return nil, err
	}

	var orgID uuid.UUID
	err = tx.QueryRow(ctx, `
		INSERT INTO organizations (name, slug) VALUES ($1, $2) RETURNING id`,
		req.OrgName, req.OrgSlug,
	).Scan(&orgID)
	if err != nil {
		return nil, fmt.Errorf("create organization: %w", err)
	}

	fullName := req.AdminFullName
	if fullName == "" {
		fullName = "Administrator"
	}

	var userID uuid.UUID
	err = tx.QueryRow(ctx, `
		INSERT INTO users (email, password_hash, full_name) VALUES ($1, $2, $3) RETURNING id`,
		strings.ToLower(strings.TrimSpace(req.AdminEmail)), hash, fullName,
	).Scan(&userID)
	if err != nil {
		return nil, fmt.Errorf("create user: %w", err)
	}

	var roleID uuid.UUID
	err = tx.QueryRow(ctx, `SELECT id FROM roles WHERE code = $1`, models.RoleSuperAdmin).Scan(&roleID)
	if err != nil {
		return nil, fmt.Errorf("lookup super_admin role: %w", err)
	}

	_, err = tx.Exec(ctx, `
		INSERT INTO org_memberships (org_id, user_id, role_id) VALUES ($1, $2, $3)`,
		orgID, userID, roleID,
	)
	if err != nil {
		return nil, fmt.Errorf("create membership: %w", err)
	}

	var siteID uuid.UUID
	err = tx.QueryRow(ctx, `
		INSERT INTO sites (org_id, name, slug, timezone) VALUES ($1, $2, $3, 'UTC') RETURNING id`,
		orgID, "Site principal", "principal",
	).Scan(&siteID)
	if err != nil {
		return nil, fmt.Errorf("create default site: %w", err)
	}

	_, err = tx.Exec(ctx, `
		UPDATE system_config SET value = '{"initialized": true}', updated_at = NOW() WHERE key = 'initialized'`)
	if err != nil {
		return nil, fmt.Errorf("mark initialized: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}

	return &models.SetupCompleteResponse{OrgID: orgID, UserID: userID, SiteID: siteID}, nil
}

type querier interface {
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
}

func (s *Service) isInitialized(ctx context.Context) (bool, error) {
	return s.isInitializedQuery(ctx, s.pool)
}

func (s *Service) isInitializedTx(ctx context.Context, q querier) (bool, error) {
	return s.isInitializedQuery(ctx, q)
}

func (s *Service) isInitializedQuery(ctx context.Context, q querier) (bool, error) {
	var value []byte
	err := q.QueryRow(ctx, `SELECT value FROM system_config WHERE key = 'initialized'`).Scan(&value)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return false, nil
		}
		return false, err
	}
	return strings.Contains(string(value), `"initialized": true`) ||
		strings.Contains(string(value), `"initialized":true`), nil
}

func normalizeRequest(req models.SetupCompleteRequest) models.SetupCompleteRequest {
	req.OrgName = strings.TrimSpace(req.OrgName)
	req.OrgSlug = strings.ToLower(strings.TrimSpace(req.OrgSlug))
	req.AdminEmail = strings.TrimSpace(req.AdminEmail)
	if req.OrgSlug == "" {
		req.OrgSlug = deriveOrgSlug(req.OrgName)
	}
	return req
}

func deriveOrgSlug(name string) string {
	s := strings.ToLower(strings.TrimSpace(name))
	var b strings.Builder
	lastDash := false
	for _, r := range s {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') {
			b.WriteRune(r)
			lastDash = false
			continue
		}
		if !lastDash && b.Len() > 0 {
			b.WriteByte('-')
			lastDash = true
		}
	}
	out := strings.Trim(b.String(), "-")
	if out == "" {
		return "org"
	}
	return out
}

func validateRequest(req models.SetupCompleteRequest) error {
	if req.OrgName == "" {
		return errors.New("org_name is required")
	}
	if req.OrgSlug == "" || !slugRe.MatchString(req.OrgSlug) {
		return errors.New("org_slug must be lowercase alphanumeric with hyphens")
	}
	if req.AdminEmail == "" || !strings.Contains(req.AdminEmail, "@") {
		return errors.New("admin_email is invalid")
	}
	if len(req.AdminPassword) < 12 {
		return errors.New("admin_password must be at least 12 characters")
	}
	if !passwordComplexEnough(req.AdminPassword) {
		return errors.New("admin_password must include upper, lower, and digit")
	}
	return nil
}

func passwordComplexEnough(password string) bool {
	var upper, lower, digit bool
	for _, r := range password {
		switch {
		case unicode.IsUpper(r):
			upper = true
		case unicode.IsLower(r):
			lower = true
		case unicode.IsDigit(r):
			digit = true
		}
	}
	return upper && lower && digit
}
