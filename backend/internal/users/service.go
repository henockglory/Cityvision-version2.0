package users

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/citevision/citevision-v2/backend/internal/auth"
	"github.com/citevision/citevision-v2/backend/internal/models"
)

var (
	ErrNotFound      = errors.New("user not found")
	ErrAlreadyMember = errors.New("user already in organization")
	ErrInvalidRole   = errors.New("invalid role")
)

type Member struct {
	ID       uuid.UUID   `json:"id"`
	Email    string      `json:"email"`
	FullName string      `json:"full_name"`
	Role     models.Role `json:"role"`
	IsActive bool        `json:"is_active"`
}

type CreateMemberRequest struct {
	Email    string      `json:"email"`
	FullName string      `json:"full_name"`
	Password string      `json:"password"`
	Role     models.Role `json:"role"`
}

type UpdateMemberRequest struct {
	Role     *models.Role `json:"role,omitempty"`
	IsActive *bool        `json:"is_active,omitempty"`
}

type Service struct {
	pool *pgxpool.Pool
}

func NewService(pool *pgxpool.Pool) *Service {
	return &Service{pool: pool}
}

func (s *Service) List(ctx context.Context, orgID uuid.UUID) ([]Member, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT u.id, u.email, u.full_name, r.code, u.is_active
		FROM org_memberships m
		JOIN users u ON u.id = m.user_id
		JOIN roles r ON r.id = m.role_id
		WHERE m.org_id = $1
		ORDER BY u.full_name, u.email`, orgID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var list []Member
	for rows.Next() {
		var m Member
		if err := rows.Scan(&m.ID, &m.Email, &m.FullName, &m.Role, &m.IsActive); err != nil {
			return nil, err
		}
		list = append(list, m)
	}
	return list, rows.Err()
}

func (s *Service) Create(ctx context.Context, orgID uuid.UUID, req CreateMemberRequest) (*Member, error) {
	email := strings.ToLower(strings.TrimSpace(req.Email))
	if email == "" || req.Password == "" || req.FullName == "" {
		return nil, fmt.Errorf("email, full_name and password are required")
	}
	role := req.Role
	if role == "" {
		role = models.RoleViewer
	}
	if !role.IsValid() {
		return nil, ErrInvalidRole
	}

	hash, err := auth.HashPassword(req.Password)
	if err != nil {
		return nil, err
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback(ctx)

	var userID uuid.UUID
	err = tx.QueryRow(ctx, `SELECT id FROM users WHERE LOWER(email) = $1`, email).Scan(&userID)
	if errors.Is(err, pgx.ErrNoRows) {
		err = tx.QueryRow(ctx, `
			INSERT INTO users (email, password_hash, full_name)
			VALUES ($1, $2, $3) RETURNING id`, email, hash, req.FullName,
		).Scan(&userID)
		if err != nil {
			return nil, fmt.Errorf("create user: %w", err)
		}
	} else if err != nil {
		return nil, err
	}

	var exists bool
	err = tx.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM org_memberships WHERE org_id = $1 AND user_id = $2)`, orgID, userID).Scan(&exists)
	if err != nil {
		return nil, err
	}
	if exists {
		return nil, ErrAlreadyMember
	}

	var roleID uuid.UUID
	err = tx.QueryRow(ctx, `SELECT id FROM roles WHERE code = $1`, role).Scan(&roleID)
	if err != nil {
		return nil, ErrInvalidRole
	}

	_, err = tx.Exec(ctx, `INSERT INTO org_memberships (org_id, user_id, role_id) VALUES ($1, $2, $3)`, orgID, userID, roleID)
	if err != nil {
		return nil, err
	}

	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}

	return &Member{
		ID: userID, Email: email, FullName: req.FullName, Role: role, IsActive: true,
	}, nil
}

func (s *Service) Update(ctx context.Context, orgID, userID uuid.UUID, req UpdateMemberRequest) (*Member, error) {
	var member Member
	err := s.pool.QueryRow(ctx, `
		SELECT u.id, u.email, u.full_name, r.code, u.is_active
		FROM org_memberships m
		JOIN users u ON u.id = m.user_id
		JOIN roles r ON r.id = m.role_id
		WHERE m.org_id = $1 AND u.id = $2`, orgID, userID,
	).Scan(&member.ID, &member.Email, &member.FullName, &member.Role, &member.IsActive)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}

	if req.IsActive != nil {
		_, err = s.pool.Exec(ctx, `UPDATE users SET is_active = $1, updated_at = NOW() WHERE id = $2`, *req.IsActive, userID)
		if err != nil {
			return nil, err
		}
		member.IsActive = *req.IsActive
	}

	if req.Role != nil {
		if !req.Role.IsValid() {
			return nil, ErrInvalidRole
		}
		var roleID uuid.UUID
		err = s.pool.QueryRow(ctx, `SELECT id FROM roles WHERE code = $1`, *req.Role).Scan(&roleID)
		if err != nil {
			return nil, ErrInvalidRole
		}
		tag, err := s.pool.Exec(ctx, `UPDATE org_memberships SET role_id = $1 WHERE org_id = $2 AND user_id = $3`, roleID, orgID, userID)
		if err != nil {
			return nil, err
		}
		if tag.RowsAffected() == 0 {
			return nil, ErrNotFound
		}
		member.Role = *req.Role
	}

	return &member, nil
}

func FrontendRoleToBackend(role string) models.Role {
	switch role {
	case "admin":
		return models.RoleOrgAdmin
	case "operator":
		return models.RoleOperator
	default:
		return models.RoleViewer
	}
}
