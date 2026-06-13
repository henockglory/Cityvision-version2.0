package rbac

import (
	"context"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/citevision/citevision-v2/backend/internal/models"
)

type Service struct {
	pool *pgxpool.Pool
}

func NewService(pool *pgxpool.Pool) *Service {
	return &Service{pool: pool}
}

func (s *Service) HasPermission(ctx context.Context, role models.Role, permission string) (bool, error) {
	var exists bool
	err := s.pool.QueryRow(ctx, `
		SELECT EXISTS(
			SELECT 1 FROM role_permissions rp
			JOIN roles r ON r.id = rp.role_id
			JOIN permissions p ON p.id = rp.permission_id
			WHERE r.code = $1 AND p.code = $2
		)`, role, permission,
	).Scan(&exists)
	return exists, err
}

func (s *Service) ListRolePermissions(ctx context.Context, role models.Role) ([]string, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT p.code FROM permissions p
		JOIN role_permissions rp ON rp.permission_id = p.id
		JOIN roles r ON r.id = rp.role_id
		WHERE r.code = $1 ORDER BY p.code`, role)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var perms []string
	for rows.Next() {
		var code string
		if err := rows.Scan(&code); err != nil {
			return nil, err
		}
		perms = append(perms, code)
	}
	return perms, rows.Err()
}

func (s *Service) GetRoleID(ctx context.Context, code models.Role) (uuid.UUID, error) {
	var id uuid.UUID
	err := s.pool.QueryRow(ctx, `SELECT id FROM roles WHERE code = $1`, code).Scan(&id)
	return id, err
}

func (s *Service) ListRoles(ctx context.Context) ([]struct {
	ID   uuid.UUID
	Code models.Role
	Name string
}, error) {
	rows, err := s.pool.Query(ctx, `SELECT id, code, name FROM roles ORDER BY code`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var roles []struct {
		ID   uuid.UUID
		Code models.Role
		Name string
	}
	for rows.Next() {
		var r struct {
			ID   uuid.UUID
			Code models.Role
			Name string
		}
		if err := rows.Scan(&r.ID, &r.Code, &r.Name); err != nil {
			return nil, err
		}
		roles = append(roles, r)
	}
	return roles, rows.Err()
}
