package state

import (
	"context"
	"encoding/json"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Snapshot struct {
	ID         uuid.UUID       `json:"id"`
	OrgID      uuid.UUID       `json:"org_id"`
	SiteID     *uuid.UUID      `json:"site_id,omitempty"`
	EntityType string          `json:"entity_type"`
	EntityID   string          `json:"entity_id"`
	State      json.RawMessage `json:"state"`
	Version    int64           `json:"version"`
}

type Service struct {
	pool *pgxpool.Pool
}

func NewService(pool *pgxpool.Pool) *Service {
	return &Service{pool: pool}
}

func (s *Service) Upsert(ctx context.Context, orgID uuid.UUID, siteID *uuid.UUID, entityType, entityID string, state json.RawMessage) (*Snapshot, error) {
	if state == nil {
		state = json.RawMessage(`{}`)
	}
	var snap Snapshot
	err := s.pool.QueryRow(ctx, `
		INSERT INTO state_snapshots (org_id, site_id, entity_type, entity_id, state)
		VALUES ($1,$2,$3,$4,$5)
		ON CONFLICT (org_id, entity_type, entity_id) DO UPDATE
		SET state = EXCLUDED.state, version = state_snapshots.version + 1, updated_at = NOW()
		RETURNING id, org_id, site_id, entity_type, entity_id, state, version`,
		orgID, siteID, entityType, entityID, state,
	).Scan(&snap.ID, &snap.OrgID, &snap.SiteID, &snap.EntityType, &snap.EntityID, &snap.State, &snap.Version)
	return &snap, err
}

func (s *Service) Get(ctx context.Context, orgID uuid.UUID, entityType, entityID string) (*Snapshot, error) {
	var snap Snapshot
	err := s.pool.QueryRow(ctx, `
		SELECT id, org_id, site_id, entity_type, entity_id, state, version
		FROM state_snapshots WHERE org_id = $1 AND entity_type = $2 AND entity_id = $3`,
		orgID, entityType, entityID,
	).Scan(&snap.ID, &snap.OrgID, &snap.SiteID, &snap.EntityType, &snap.EntityID, &snap.State, &snap.Version)
	if err != nil {
		return nil, err
	}
	return &snap, nil
}

func (s *Service) ListByType(ctx context.Context, orgID uuid.UUID, entityType string) ([]Snapshot, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, org_id, site_id, entity_type, entity_id, state, version
		FROM state_snapshots WHERE org_id = $1 AND entity_type = $2`, orgID, entityType)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var list []Snapshot
	for rows.Next() {
		var snap Snapshot
		if err := rows.Scan(&snap.ID, &snap.OrgID, &snap.SiteID, &snap.EntityType, &snap.EntityID, &snap.State, &snap.Version); err != nil {
			return nil, err
		}
		list = append(list, snap)
	}
	return list, rows.Err()
}
