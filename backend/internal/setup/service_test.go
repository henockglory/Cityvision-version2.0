package setup_test

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/citevision/citevision-v2/backend/internal/db"
	"github.com/citevision/citevision-v2/backend/internal/models"
	"github.com/citevision/citevision-v2/backend/internal/setup"
)

func testEnv(t *testing.T) (*pgxpool.Pool, *setup.Service) {
	t.Helper()
	url := os.Getenv("TEST_POSTGRES_URL")
	if url == "" {
		t.Skip("TEST_POSTGRES_URL not set")
	}
	ctx := context.Background()
	pool, err := db.Connect(ctx, url)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)

	migrationsPath := findMigrations(t)
	if err := db.Migrate(url, migrationsPath); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	_, _ = pool.Exec(ctx, `TRUNCATE audit_logs RESTART IDENTITY`)
	_, _ = pool.Exec(ctx, `TRUNCATE org_memberships, users, organizations CASCADE`)
	_, _ = pool.Exec(ctx, `UPDATE system_config SET value = '{"initialized": false}' WHERE key = 'initialized'`)
	return pool, setup.NewService(pool)
}

func findMigrations(t *testing.T) string {
	t.Helper()
	wd, _ := os.Getwd()
	candidates := []string{
		filepath.Join(wd, "migrations"),
		filepath.Join(wd, "..", "..", "migrations"),
		filepath.Join(wd, "..", "migrations"),
	}
	for _, p := range candidates {
		if _, err := os.Stat(p); err == nil {
			abs, _ := filepath.Abs(p)
			return abs
		}
	}
	t.Fatal("migrations path not found")
	return ""
}

func TestSetupStatusNotInitialized(t *testing.T) {
	_, svc := testEnv(t)
	status, err := svc.Status(context.Background())
	if err != nil {
		t.Fatalf("status: %v", err)
	}
	if status.Initialized {
		t.Fatal("expected not initialized")
	}
}

func TestSetupCompleteCreatesExactlyOneOrgAndUser(t *testing.T) {
	pool, svc := testEnv(t)
	ctx := context.Background()

	resp, err := svc.Complete(ctx, models.SetupCompleteRequest{
		OrgName:       "Acme Security",
		OrgSlug:       "acme",
		AdminEmail:    "admin@acme.test",
		AdminPassword: "SecurePass123!",
		AdminFullName: "Admin User",
	})
	if err != nil {
		t.Fatalf("complete: %v", err)
	}
	if resp.OrgID.String() == "" || resp.UserID.String() == "" {
		t.Fatal("expected org and user ids")
	}

	status, err := svc.Status(ctx)
	if err != nil {
		t.Fatalf("status after: %v", err)
	}
	if !status.Initialized {
		t.Fatal("expected initialized true")
	}

	var orgCount, userCount, membershipCount int
	if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM organizations`).Scan(&orgCount); err != nil {
		t.Fatal(err)
	}
	if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM users`).Scan(&userCount); err != nil {
		t.Fatal(err)
	}
	if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM org_memberships`).Scan(&membershipCount); err != nil {
		t.Fatal(err)
	}
	if orgCount != 1 || userCount != 1 || membershipCount != 1 {
		t.Fatalf("expected 1 org, 1 user, 1 membership; got org=%d user=%d membership=%d", orgCount, userCount, membershipCount)
	}
}

func TestSetupCompleteRejectsWhenInitialized(t *testing.T) {
	_, svc := testEnv(t)
	ctx := context.Background()

	req := models.SetupCompleteRequest{
		OrgName:       "First Org",
		OrgSlug:       "first",
		AdminEmail:    "first@test.local",
		AdminPassword: "SecurePass123!",
	}
	if _, err := svc.Complete(ctx, req); err != nil {
		t.Fatalf("first complete: %v", err)
	}

	_, err := svc.Complete(ctx, models.SetupCompleteRequest{
		OrgName:       "Second Org",
		OrgSlug:       "second",
		AdminEmail:    "second@test.local",
		AdminPassword: "SecurePass123!",
	})
	if err != setup.ErrAlreadyInitialized {
		t.Fatalf("expected ErrAlreadyInitialized, got %v", err)
	}
}

func TestSetupCompleteValidatesPassword(t *testing.T) {
	_, svc := testEnv(t)
	_, err := svc.Complete(context.Background(), models.SetupCompleteRequest{
		OrgName:       "Acme",
		OrgSlug:       "acme",
		AdminEmail:    "admin@test.local",
		AdminPassword: "short",
	})
	if err == nil {
		t.Fatal("expected validation error")
	}
}
