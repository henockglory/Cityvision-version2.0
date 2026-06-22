package audit

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/citevision/citevision-v2/backend/internal/models"
)

type Service struct {
	pool    *pgxpool.Pool
	signKey []byte
}

func NewService(pool *pgxpool.Pool, signKey string) *Service {
	return &Service{pool: pool, signKey: []byte(signKey)}
}

type LogRequest struct {
	OrgID        *uuid.UUID
	UserID       *uuid.UUID
	Action       string
	ResourceType string
	ResourceID   *string
	IPAddress    net.IP
	UserAgent    string
	Payload      map[string]interface{}
}

func (s *Service) Append(ctx context.Context, req LogRequest) (*models.AuditEntry, error) {
	var prevHash string
	err := s.pool.QueryRow(ctx, `SELECT COALESCE(entry_hash, '') FROM audit_logs ORDER BY id DESC LIMIT 1`).Scan(&prevHash)
	if err != nil {
		prevHash = ""
	}

	payloadJSON, err := json.Marshal(req.Payload)
	if err != nil {
		payloadJSON = []byte("{}")
	}

	now := time.Now().UTC()
	entryHash := s.computeHash(prevHash, req, payloadJSON, now)

	var ipStr *string
	if req.IPAddress != nil {
		s := req.IPAddress.String()
		ipStr = &s
	}
	var ua *string
	if req.UserAgent != "" {
		ua = &req.UserAgent
	}

	var entry models.AuditEntry
	err = s.pool.QueryRow(ctx, `
		INSERT INTO audit_logs (org_id, user_id, action, resource_type, resource_id, ip_address, user_agent, payload, prev_hash, entry_hash, created_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
		RETURNING id, org_id, user_id, action, resource_type, resource_id, ip_address::text, user_agent, payload, prev_hash, entry_hash, created_at`,
		req.OrgID, req.UserID, req.Action, req.ResourceType, req.ResourceID,
		ipStr, ua, payloadJSON, prevHash, entryHash, now,
	).Scan(
		&entry.ID, &entry.OrgID, &entry.UserID, &entry.Action, &entry.ResourceType,
		&entry.ResourceID, &entry.IPAddress, &entry.UserAgent, &entry.Payload,
		&entry.PrevHash, &entry.EntryHash, &entry.CreatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("append audit log: %w", err)
	}
	return &entry, nil
}

func (s *Service) computeHash(prevHash string, req LogRequest, payload []byte, ts time.Time) string {
	mac := hmac.New(sha256.New, s.signKey)
	uid := ""
	if req.UserID != nil {
		uid = req.UserID.String()
	}
	data := fmt.Sprintf("%s|%s|%s|%s|%s|%s",
		prevHash, req.Action, req.ResourceType, string(payload), ts.Format(time.RFC3339Nano), uid,
	)
	mac.Write([]byte(data))
	return hex.EncodeToString(mac.Sum(nil))
}

type AuditListEntry struct {
	models.AuditEntry
	UserEmail string `json:"user_email,omitempty"`
	UserName  string `json:"user_name,omitempty"`
}

func (s *Service) ListEnriched(ctx context.Context, orgID uuid.UUID, limit, offset int, actionFilter string) ([]AuditListEntry, error) {
	if limit <= 0 {
		limit = 100
	}
	q := `
		SELECT a.id, a.org_id, a.user_id, a.action, a.resource_type, a.resource_id,
			a.ip_address::text, a.user_agent, a.payload, a.prev_hash, a.entry_hash, a.created_at,
			COALESCE(u.email, ''), COALESCE(u.full_name, '')
		FROM audit_logs a
		LEFT JOIN users u ON u.id = a.user_id
		WHERE a.org_id = $1`
	args := []interface{}{orgID}
	n := 2
	if actionFilter != "" {
		q += fmt.Sprintf(` AND UPPER(a.action) = UPPER($%d)`, n)
		args = append(args, actionFilter)
		n++
	}
	q += fmt.Sprintf(` ORDER BY a.id DESC LIMIT $%d OFFSET $%d`, n, n+1)
	args = append(args, limit, offset)

	rows, err := s.pool.Query(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var entries []AuditListEntry
	for rows.Next() {
		var e AuditListEntry
		if err := rows.Scan(
			&e.ID, &e.OrgID, &e.UserID, &e.Action, &e.ResourceType, &e.ResourceID,
			&e.IPAddress, &e.UserAgent, &e.Payload, &e.PrevHash, &e.EntryHash, &e.CreatedAt,
			&e.UserEmail, &e.UserName,
		); err != nil {
			return nil, err
		}
		entries = append(entries, e)
	}
	return entries, rows.Err()
}

func (s *Service) VerifyChain(ctx context.Context, limit int) (bool, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, org_id, user_id, action, resource_type, resource_id, payload, prev_hash, entry_hash, created_at
		FROM audit_logs ORDER BY id ASC LIMIT $1`, limit)
	if err != nil {
		return false, err
	}
	defer rows.Close()

	var prevHash string
	for rows.Next() {
		var entry models.AuditEntry
		var orgID, userID *uuid.UUID
		var resourceID *string
		if err := rows.Scan(&entry.ID, &orgID, &userID, &entry.Action, &entry.ResourceType,
			&resourceID, &entry.Payload, &entry.PrevHash, &entry.EntryHash, &entry.CreatedAt); err != nil {
			return false, err
		}
		if entry.PrevHash != prevHash {
			return false, nil
		}
		uid := ""
		if userID != nil {
			uid = userID.String()
		}
		mac := hmac.New(sha256.New, s.signKey)
		data := fmt.Sprintf("%s|%s|%s|%s|%s|%s",
			entry.PrevHash, entry.Action, entry.ResourceType, string(entry.Payload),
			entry.CreatedAt.Format(time.RFC3339Nano), uid)
		mac.Write([]byte(data))
		if hex.EncodeToString(mac.Sum(nil)) != entry.EntryHash {
			return false, nil
		}
		prevHash = entry.EntryHash
	}
	return true, rows.Err()
}

func (s *Service) List(ctx context.Context, orgID uuid.UUID, limit, offset int) ([]models.AuditEntry, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, org_id, user_id, action, resource_type, resource_id, ip_address::text, user_agent, payload, prev_hash, entry_hash, created_at
		FROM audit_logs WHERE org_id = $1 ORDER BY id DESC LIMIT $2 OFFSET $3`, orgID, limit, offset)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var entries []models.AuditEntry
	for rows.Next() {
		var e models.AuditEntry
		if err := rows.Scan(&e.ID, &e.OrgID, &e.UserID, &e.Action, &e.ResourceType, &e.ResourceID,
			&e.IPAddress, &e.UserAgent, &e.Payload, &e.PrevHash, &e.EntryHash, &e.CreatedAt); err != nil {
			return nil, err
		}
		entries = append(entries, e)
	}
	return entries, rows.Err()
}
