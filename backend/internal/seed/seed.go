package seed

import (
	"context"
	"log/slog"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/citevision/citevision/backend/internal/auth"
	"github.com/citevision/citevision/backend/internal/models"
)

type Config struct {
	AdminEmail    string
	AdminPassword string
	TenantName    string
	TenantSlug    string
}

func Run(ctx context.Context, pool *pgxpool.Pool, cfg Config, log *slog.Logger) error {
	if cfg.AdminEmail == "" || cfg.AdminPassword == "" {
		log.Info("seed skipped: SEED_ADMIN_EMAIL or SEED_ADMIN_PASSWORD not set")
		return nil
	}

	var exists bool
	err := pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM users WHERE email = $1)`, cfg.AdminEmail).Scan(&exists)
	if err != nil {
		return err
	}
	if exists {
		log.Info("seed skipped: admin user already exists")
		return nil
	}

	hash, err := auth.HashPassword(cfg.AdminPassword)
	if err != nil {
		return err
	}

	tx, err := pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	var orgID uuid.UUID
	err = tx.QueryRow(ctx, `
		INSERT INTO organizations (name, slug) VALUES ($1, $2)
		ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
		RETURNING id`, cfg.TenantName, cfg.TenantSlug,
	).Scan(&orgID)
	if err != nil {
		return err
	}

	var userID uuid.UUID
	err = tx.QueryRow(ctx, `
		INSERT INTO users (email, password_hash, full_name)
		VALUES ($1, $2, $3) RETURNING id`,
		cfg.AdminEmail, hash, "Seed Admin",
	).Scan(&userID)
	if err != nil {
		return err
	}

	_, err = tx.Exec(ctx, `
		INSERT INTO org_memberships (org_id, user_id, role)
		VALUES ($1, $2, $3) ON CONFLICT DO NOTHING`,
		orgID, userID, models.RoleSuperAdmin,
	)
	if err != nil {
		return err
	}

	var siteID uuid.UUID
	err = tx.QueryRow(ctx, `
		INSERT INTO sites (org_id, name, slug, timezone)
		VALUES ($1, 'Main Site', 'main', 'UTC')
		ON CONFLICT (org_id, slug) DO UPDATE SET name = EXCLUDED.name
		RETURNING id`, orgID,
	).Scan(&siteID)
	if err != nil {
		return err
	}

	if err := tx.Commit(ctx); err != nil {
		return err
	}

	log.Info("seed completed", "org_id", orgID, "user_id", userID, "site_id", siteID)
	return nil
}
