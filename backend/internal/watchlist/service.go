package watchlist

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/citevision/citevision/backend/internal/models"
)

var ErrNotFound = errors.New("watchlist entry not found")

type CreateRequest struct {
	OrgID      uuid.UUID       `json:"org_id"`
	EntryType  string          `json:"entry_type"` // face, anpr
	Label      string          `json:"label"`
	Identifier string          `json:"identifier"`
	Metadata   json.RawMessage `json:"metadata"`
}

type Service struct {
	pool *pgxpool.Pool
}

func NewService(pool *pgxpool.Pool) *Service {
	return &Service{pool: pool}
}

func (s *Service) Create(ctx context.Context, req CreateRequest) (*models.WatchlistEntry, error) {
	meta := req.Metadata
	if meta == nil {
		meta = json.RawMessage(`{}`)
	}
	var e models.WatchlistEntry
	err := s.pool.QueryRow(ctx, `
		INSERT INTO watchlist_entries (org_id, entry_type, label, identifier, metadata)
		VALUES ($1,$2,$3,$4,$5)
		RETURNING id, org_id, entry_type, label, identifier, metadata, is_active, created_at, updated_at`,
		req.OrgID, req.EntryType, req.Label, req.Identifier, meta,
	).Scan(&e.ID, &e.OrgID, &e.EntryType, &e.Label, &e.Identifier, &e.Metadata, &e.IsActive, &e.CreatedAt, &e.UpdatedAt)
	return &e, err
}

func (s *Service) List(ctx context.Context, orgID uuid.UUID, entryType string) ([]models.WatchlistEntry, error) {
	q := `SELECT id, org_id, entry_type, label, identifier, metadata, is_active, created_at, updated_at FROM watchlist_entries WHERE org_id = $1`
	args := []interface{}{orgID}
	if entryType != "" {
		q += ` AND entry_type = $2`
		args = append(args, entryType)
	}
	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var list []models.WatchlistEntry
	for rows.Next() {
		var e models.WatchlistEntry
		if err := rows.Scan(&e.ID, &e.OrgID, &e.EntryType, &e.Label, &e.Identifier, &e.Metadata, &e.IsActive, &e.CreatedAt, &e.UpdatedAt); err != nil {
			return nil, err
		}
		list = append(list, e)
	}
	return list, rows.Err()
}

func (s *Service) Get(ctx context.Context, orgID, id uuid.UUID) (*models.WatchlistEntry, error) {
	var e models.WatchlistEntry
	err := s.pool.QueryRow(ctx, `
		SELECT id, org_id, entry_type, label, identifier, metadata, is_active, created_at, updated_at
		FROM watchlist_entries WHERE id = $1 AND org_id = $2`, id, orgID,
	).Scan(&e.ID, &e.OrgID, &e.EntryType, &e.Label, &e.Identifier, &e.Metadata, &e.IsActive, &e.CreatedAt, &e.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	return &e, err
}

func (s *Service) Delete(ctx context.Context, orgID, id uuid.UUID) error {
	tag, err := s.pool.Exec(ctx, `DELETE FROM watchlist_entries WHERE id = $1 AND org_id = $2`, id, orgID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

// MatchFace stub: returns whether identifier is on watchlist.
func (s *Service) MatchFace(ctx context.Context, orgID uuid.UUID, faceEmbeddingID string) (*models.WatchlistEntry, error) {
	entries, err := s.List(ctx, orgID, "face")
	if err != nil {
		return nil, err
	}
	for _, e := range entries {
		if e.Identifier == faceEmbeddingID && e.IsActive {
			return &e, nil
		}
	}
	return nil, ErrNotFound
}

// MatchANPR stub: plate lookup.
func (s *Service) MatchANPR(ctx context.Context, orgID uuid.UUID, plate string) (*models.WatchlistEntry, error) {
	entries, err := s.List(ctx, orgID, "anpr")
	if err != nil {
		return nil, err
	}
	for _, e := range entries {
		if e.Identifier == plate && e.IsActive {
			return &e, nil
		}
	}
	return nil, ErrNotFound
}
