package org

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrNotFound = errors.New("organization not found")

type Organization struct {
	ID                uuid.UUID       `json:"id"`
	Name              string          `json:"name"`
	Slug              string          `json:"slug"`
	Timezone          string          `json:"timezone"`
	LogoURL           *string         `json:"logo_url,omitempty"`
	NotificationPrefs json.RawMessage `json:"notification_prefs"`
	SecurityPrefs     json.RawMessage `json:"security_prefs"`
	SMTPConfig        json.RawMessage `json:"smtp_config"`
}

type UpdateRequest struct {
	Name              *string          `json:"name,omitempty"`
	Timezone          *string          `json:"timezone,omitempty"`
	LogoURL           *string          `json:"logo_url,omitempty"`
	NotificationPrefs *json.RawMessage `json:"notification_prefs,omitempty"`
	SecurityPrefs     *json.RawMessage `json:"security_prefs,omitempty"`
	SMTPConfig        *json.RawMessage `json:"smtp_config,omitempty"`
}

type Service struct {
	pool *pgxpool.Pool
}

func NewService(pool *pgxpool.Pool) *Service {
	return &Service{pool: pool}
}

func (s *Service) Get(ctx context.Context, id uuid.UUID) (*Organization, error) {
	var o Organization
	err := s.pool.QueryRow(ctx, `
		SELECT id, name, slug,
			COALESCE(timezone, 'Africa/Kinshasa'),
			logo_url,
			COALESCE(notification_prefs, '{}'),
			COALESCE(security_prefs, '{}'),
			COALESCE(smtp_config, '{}')
		FROM organizations WHERE id = $1`, id,
	).Scan(&o.ID, &o.Name, &o.Slug, &o.Timezone, &o.LogoURL, &o.NotificationPrefs, &o.SecurityPrefs, &o.SMTPConfig)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	return &o, err
}

func (s *Service) Update(ctx context.Context, id uuid.UUID, req UpdateRequest) (*Organization, error) {
	q := `UPDATE organizations SET updated_at = NOW()`
	args := []interface{}{}
	n := 1
	if req.Name != nil {
		q += `, name = $` + itoa(n)
		args = append(args, *req.Name)
		n++
	}
	if req.Timezone != nil {
		q += `, timezone = $` + itoa(n)
		args = append(args, *req.Timezone)
		n++
	}
	if req.LogoURL != nil {
		q += `, logo_url = $` + itoa(n)
		args = append(args, *req.LogoURL)
		n++
	}
	if req.NotificationPrefs != nil {
		q += `, notification_prefs = $` + itoa(n)
		args = append(args, *req.NotificationPrefs)
		n++
	}
	if req.SecurityPrefs != nil {
		q += `, security_prefs = $` + itoa(n)
		args = append(args, *req.SecurityPrefs)
		n++
	}
	if req.SMTPConfig != nil {
		q += `, smtp_config = $` + itoa(n)
		args = append(args, *req.SMTPConfig)
		n++
	}
	q += ` WHERE id = $` + itoa(n) + ` RETURNING id, name, slug,
		COALESCE(timezone, 'Africa/Kinshasa'), logo_url,
		COALESCE(notification_prefs, '{}'),
		COALESCE(security_prefs, '{}'),
		COALESCE(smtp_config, '{}')`
	args = append(args, id)

	var o Organization
	err := s.pool.QueryRow(ctx, q, args...).Scan(
		&o.ID, &o.Name, &o.Slug, &o.Timezone, &o.LogoURL,
		&o.NotificationPrefs, &o.SecurityPrefs, &o.SMTPConfig,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	return &o, err
}

func itoa(n int) string {
	return fmt.Sprintf("%d", n)
}
