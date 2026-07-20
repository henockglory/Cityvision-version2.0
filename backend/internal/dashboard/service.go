package dashboard

import (
	"context"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Summary struct {
	CamerasActive  int `json:"cameras_active"`
	CamerasTotal   int `json:"cameras_total"`
	OpenAlerts     int `json:"open_alerts"`
	EventsLast24h  int `json:"events_last_24h"`
	RulesEnabled   int `json:"rules_enabled"`
	UsersTotal     int `json:"users_total"`
}

type Service struct {
	pool *pgxpool.Pool
}

func NewService(pool *pgxpool.Pool) *Service {
	return &Service{pool: pool}
}

func (s *Service) Summary(ctx context.Context, orgID uuid.UUID) (*Summary, error) {
	var sum Summary
	err := s.pool.QueryRow(ctx, `
		SELECT
			(SELECT COUNT(*)::int FROM cameras WHERE org_id = $1 AND status = 'online'),
			(SELECT COUNT(*)::int FROM cameras WHERE org_id = $1),
			(SELECT COUNT(*)::int FROM alerts WHERE org_id = $1 AND status = 'open'),
			(SELECT COUNT(*)::int FROM events WHERE org_id = $1 AND occurred_at >= NOW() - INTERVAL '24 hours'),
			(SELECT COUNT(*)::int FROM rules WHERE org_id = $1 AND is_enabled = TRUE),
			(SELECT COUNT(*)::int FROM org_memberships WHERE org_id = $1)
	`, orgID).Scan(
		&sum.CamerasActive,
		&sum.CamerasTotal,
		&sum.OpenAlerts,
		&sum.EventsLast24h,
		&sum.RulesEnabled,
		&sum.UsersTotal,
	)
	if err != nil {
		return nil, err
	}
	return &sum, nil
}
