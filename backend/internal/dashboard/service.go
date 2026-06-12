package dashboard

import (
	"context"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Summary struct {
	OrgID           uuid.UUID `json:"org_id"`
	CamerasActive   int       `json:"cameras_active"`
	CamerasTotal    int       `json:"cameras_total"`
	OpenAlerts      int       `json:"open_alerts"`
	OpenIncidents   int       `json:"open_incidents"`
	EventsLast24h   int       `json:"events_last_24h"`
	SitesTotal      int       `json:"sites_total"`
	UsersTotal      int       `json:"users_total"`
	RulesEnabled    int       `json:"rules_enabled"`
	GeneratedAt     time.Time `json:"generated_at"`
}

type Service struct {
	pool *pgxpool.Pool
}

func NewService(pool *pgxpool.Pool) *Service {
	return &Service{pool: pool}
}

func (s *Service) GetSummary(ctx context.Context, orgID uuid.UUID) (*Summary, error) {
	summary := &Summary{
		OrgID:       orgID,
		GeneratedAt: time.Now().UTC(),
	}

	err := s.pool.QueryRow(ctx, `
		SELECT
			(SELECT COUNT(*) FROM cameras WHERE org_id = $1 AND is_active = TRUE),
			(SELECT COUNT(*) FROM cameras WHERE org_id = $1),
			(SELECT COUNT(*) FROM alerts WHERE org_id = $1 AND status = 'open'),
			(SELECT COUNT(*) FROM incidents WHERE org_id = $1 AND status IN ('open','investigating')),
			(SELECT COUNT(*) FROM events WHERE org_id = $1 AND occurred_at >= NOW() - INTERVAL '24 hours'),
			(SELECT COUNT(*) FROM sites WHERE org_id = $1 AND is_active = TRUE),
			(SELECT COUNT(*) FROM org_memberships WHERE org_id = $1),
			(SELECT COUNT(*) FROM rules WHERE org_id = $1 AND is_enabled = TRUE)`,
		orgID,
	).Scan(
		&summary.CamerasActive, &summary.CamerasTotal, &summary.OpenAlerts,
		&summary.OpenIncidents, &summary.EventsLast24h, &summary.SitesTotal,
		&summary.UsersTotal, &summary.RulesEnabled,
	)
	if err != nil {
		return nil, err
	}
	return summary, nil
}
