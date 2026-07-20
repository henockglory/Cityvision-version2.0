package identity

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrNotFound = errors.New("list not found")

type List struct {
	ID        uuid.UUID       `json:"id"`
	OrgID     uuid.UUID       `json:"org_id"`
	Name      string          `json:"name"`
	ListType  string          `json:"list_type"`
	Entries   json.RawMessage `json:"entries"`
	IsActive  bool            `json:"is_active"`
	CreatedAt string          `json:"created_at,omitempty"`
	UpdatedAt string          `json:"updated_at,omitempty"`
}

type CreateRequest struct {
	Name     string          `json:"name"`
	ListType string          `json:"list_type"`
	Entries  json.RawMessage `json:"entries,omitempty"`
}

type Service struct {
	pool *pgxpool.Pool
}

func NewService(pool *pgxpool.Pool) *Service {
	return &Service{pool: pool}
}

func (s *Service) List(ctx context.Context, orgID uuid.UUID, listType string) ([]List, error) {
	q := `SELECT id, org_id, name, list_type, entries, is_active, created_at::text, updated_at::text
		FROM surveillance_lists WHERE org_id = $1`
	args := []interface{}{orgID}
	if listType != "" {
		q += ` AND list_type = $2`
		args = append(args, listType)
	}
	q += ` ORDER BY name`
	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []List
	for rows.Next() {
		var l List
		if err := rows.Scan(&l.ID, &l.OrgID, &l.Name, &l.ListType, &l.Entries, &l.IsActive, &l.CreatedAt, &l.UpdatedAt); err != nil {
			return nil, err
		}
		out = append(out, l)
	}
	return out, rows.Err()
}

func (s *Service) Create(ctx context.Context, orgID uuid.UUID, req CreateRequest) (*List, error) {
	entries := req.Entries
	if len(entries) == 0 {
		entries = json.RawMessage(`[]`)
	}
	var l List
	err := s.pool.QueryRow(ctx, `
		INSERT INTO surveillance_lists (org_id, name, list_type, entries)
		VALUES ($1,$2,$3,$4)
		RETURNING id, org_id, name, list_type, entries, is_active, created_at::text, updated_at::text`,
		orgID, req.Name, req.ListType, entries,
	).Scan(&l.ID, &l.OrgID, &l.Name, &l.ListType, &l.Entries, &l.IsActive, &l.CreatedAt, &l.UpdatedAt)
	return &l, err
}

func (s *Service) Delete(ctx context.Context, orgID, id uuid.UUID) error {
	tag, err := s.pool.Exec(ctx, `DELETE FROM surveillance_lists WHERE id = $1 AND org_id = $2`, id, orgID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (s *Service) CountEntries(ctx context.Context, orgID uuid.UUID, listType string) (int, error) {
	var n int
	err := s.pool.QueryRow(ctx, `
		SELECT COALESCE(SUM(jsonb_array_length(entries)), 0)::int
		FROM surveillance_lists WHERE org_id = $1 AND list_type = $2 AND is_active = TRUE`,
		orgID, listType,
	).Scan(&n)
	return n, err
}

func (s *Service) Get(ctx context.Context, orgID, id uuid.UUID) (*List, error) {
	var l List
	err := s.pool.QueryRow(ctx, `
		SELECT id, org_id, name, list_type, entries, is_active, created_at::text, updated_at::text
		FROM surveillance_lists WHERE id = $1 AND org_id = $2`, id, orgID,
	).Scan(&l.ID, &l.OrgID, &l.Name, &l.ListType, &l.Entries, &l.IsActive, &l.CreatedAt, &l.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	return &l, err
}

func (s *Service) AppendEntry(ctx context.Context, orgID, listID uuid.UUID, entry map[string]interface{}) (*List, error) {
	l, err := s.Get(ctx, orgID, listID)
	if err != nil {
		return nil, err
	}
	var entries []map[string]interface{}
	_ = json.Unmarshal(l.Entries, &entries)
	entries = append(entries, entry)
	updated, _ := json.Marshal(entries)
	var out List
	err = s.pool.QueryRow(ctx, `
		UPDATE surveillance_lists SET entries = $1, updated_at = NOW()
		WHERE id = $2 AND org_id = $3
		RETURNING id, org_id, name, list_type, entries, is_active, created_at::text, updated_at::text`,
		updated, listID, orgID,
	).Scan(&out.ID, &out.OrgID, &out.Name, &out.ListType, &out.Entries, &out.IsActive, &out.CreatedAt, &out.UpdatedAt)
	return &out, err
}
