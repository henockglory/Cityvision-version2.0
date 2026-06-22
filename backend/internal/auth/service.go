package auth

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"golang.org/x/crypto/bcrypt"

	"github.com/citevision/citevision-v2/backend/internal/models"
	redisstore "github.com/citevision/citevision-v2/backend/internal/redis"
)

var (
	ErrInvalidCredentials = errors.New("invalid credentials")
	ErrInvalidToken       = errors.New("invalid token")
	ErrTokenRevoked       = errors.New("token revoked")
	ErrTOTPRequired       = errors.New("totp required")
	ErrInvalidTOTP        = errors.New("invalid totp code")
	ErrSessionNotFound    = errors.New("session not found")
)

type TokenPair struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	SessionID    string `json:"session_id"`
	ExpiresIn    int64  `json:"expires_in"`
}

type Claims struct {
	jwt.RegisteredClaims
	UserID    uuid.UUID   `json:"uid"`
	Email     string      `json:"email"`
	OrgID     *uuid.UUID  `json:"org_id,omitempty"`
	Role      models.Role `json:"role,omitempty"`
	SessionID string      `json:"sid"`
}

type Service struct {
	pool       *pgxpool.Pool
	sessions   *redisstore.Client
	secret     []byte
	accessTTL  time.Duration
	refreshTTL time.Duration
}

func NewService(pool *pgxpool.Pool, sessions *redisstore.Client, secret string, accessTTL, refreshTTL time.Duration) *Service {
	return &Service{
		pool:       pool,
		sessions:   sessions,
		secret:     []byte(secret),
		accessTTL:  accessTTL,
		refreshTTL: refreshTTL,
	}
}

func HashPassword(password string) (string, error) {
	hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return "", err
	}
	return string(hash), nil
}

func CheckPassword(hash, password string) bool {
	return bcrypt.CompareHashAndPassword([]byte(hash), []byte(password)) == nil
}

func (s *Service) Login(ctx context.Context, email, password, totpCode string) (*TokenPair, *models.User, error) {
	var u models.User
	err := s.pool.QueryRow(ctx, `
		SELECT id, email, password_hash, full_name, is_active, totp_enabled, totp_secret, created_at, updated_at
		FROM users WHERE LOWER(email) = LOWER($1)`, email,
	).Scan(&u.ID, &u.Email, &u.PasswordHash, &u.FullName, &u.IsActive, &u.TOTPEnabled, &u.TOTPSecret, &u.CreatedAt, &u.UpdatedAt)
	if err != nil {
		return nil, nil, ErrInvalidCredentials
	}
	if !u.IsActive || !CheckPassword(u.PasswordHash, password) {
		return nil, nil, ErrInvalidCredentials
	}
	if u.TOTPEnabled {
		if totpCode == "" {
			return nil, nil, ErrTOTPRequired
		}
		if u.TOTPSecret == nil || !ValidateTOTP(*u.TOTPSecret, totpCode) {
			return nil, nil, ErrInvalidTOTP
		}
	}

	var orgID uuid.UUID
	var role models.Role
	err = s.pool.QueryRow(ctx, `
		SELECT om.org_id, r.code
		FROM org_memberships om
		JOIN roles r ON r.id = om.role_id
		WHERE om.user_id = $1
		ORDER BY om.created_at LIMIT 1`, u.ID,
	).Scan(&orgID, &role)
	var orgPtr *uuid.UUID
	if err == nil {
		orgPtr = &orgID
	} else {
		role = models.RoleViewer
	}

	pair, err := s.issueTokens(ctx, u, orgPtr, role)
	if err != nil {
		return nil, nil, err
	}
	return pair, &u, nil
}

func (s *Service) GetUserByID(ctx context.Context, userID uuid.UUID) (*models.User, error) {
	var u models.User
	err := s.pool.QueryRow(ctx, `
		SELECT id, email, full_name, is_active, totp_enabled, created_at, updated_at
		FROM users WHERE id = $1`, userID,
	).Scan(&u.ID, &u.Email, &u.FullName, &u.IsActive, &u.TOTPEnabled, &u.CreatedAt, &u.UpdatedAt)
	if err != nil {
		return nil, ErrInvalidCredentials
	}
	return &u, nil
}

func (s *Service) PrimaryOrgID(ctx context.Context, userID uuid.UUID) *uuid.UUID {
	var orgID uuid.UUID
	err := s.pool.QueryRow(ctx, `
		SELECT org_id FROM org_memberships WHERE user_id = $1 ORDER BY created_at LIMIT 1`, userID,
	).Scan(&orgID)
	if err != nil {
		return nil
	}
	return &orgID
}

func (s *Service) issueTokens(ctx context.Context, u models.User, orgID *uuid.UUID, role models.Role) (*TokenPair, error) {
	sessionID, err := s.sessions.CreateSession(ctx, redisstore.Session{
		UserID:    u.ID,
		Email:     u.Email,
		OrgID:     orgID,
		Role:      role,
		CreatedAt: time.Now().UTC(),
	})
	if err != nil {
		return nil, fmt.Errorf("create session: %w", err)
	}

	now := time.Now()
	accessClaims := Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   u.ID.String(),
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(now.Add(s.accessTTL)),
			ID:        uuid.New().String(),
		},
		UserID:    u.ID,
		Email:     u.Email,
		OrgID:     orgID,
		Role:      role,
		SessionID: sessionID,
	}
	accessToken := jwt.NewWithClaims(jwt.SigningMethodHS256, accessClaims)
	accessStr, err := accessToken.SignedString(s.secret)
	if err != nil {
		return nil, err
	}

	refreshRaw := make([]byte, 32)
	if _, err := rand.Read(refreshRaw); err != nil {
		return nil, err
	}
	refreshStr := hex.EncodeToString(refreshRaw)
	refreshHash := hashToken(refreshStr)

	_, err = s.pool.Exec(ctx, `
		INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
		VALUES ($1, $2, $3)`, u.ID, refreshHash, now.Add(s.refreshTTL))
	if err != nil {
		return nil, err
	}

	return &TokenPair{
		AccessToken:  accessStr,
		RefreshToken: refreshStr,
		SessionID:    sessionID,
		ExpiresIn:    int64(s.accessTTL.Seconds()),
	}, nil
}

func hashToken(token string) string {
	h := sha256.Sum256([]byte(token))
	return hex.EncodeToString(h[:])
}

func (s *Service) Refresh(ctx context.Context, refreshToken string) (*TokenPair, error) {
	hash := hashToken(refreshToken)
	var userID uuid.UUID
	var revokedAt *time.Time
	var expiresAt time.Time
	err := s.pool.QueryRow(ctx, `
		SELECT user_id, revoked_at, expires_at FROM refresh_tokens WHERE token_hash = $1`, hash,
	).Scan(&userID, &revokedAt, &expiresAt)
	if err != nil {
		return nil, ErrInvalidToken
	}
	if revokedAt != nil || time.Now().After(expiresAt) {
		return nil, ErrTokenRevoked
	}

	var u models.User
	err = s.pool.QueryRow(ctx, `
		SELECT id, email, password_hash, full_name, is_active, totp_enabled, totp_secret, created_at, updated_at
		FROM users WHERE id = $1 AND is_active = TRUE`, userID,
	).Scan(&u.ID, &u.Email, &u.PasswordHash, &u.FullName, &u.IsActive, &u.TOTPEnabled, &u.TOTPSecret, &u.CreatedAt, &u.UpdatedAt)
	if err != nil {
		return nil, ErrInvalidToken
	}

	var orgID uuid.UUID
	var role models.Role
	err = s.pool.QueryRow(ctx, `
		SELECT om.org_id, r.code
		FROM org_memberships om
		JOIN roles r ON r.id = om.role_id
		WHERE om.user_id = $1 ORDER BY om.created_at LIMIT 1`, u.ID,
	).Scan(&orgID, &role)
	var orgPtr *uuid.UUID
	if err == nil {
		orgPtr = &orgID
	} else {
		role = models.RoleViewer
	}

	_, _ = s.pool.Exec(ctx, `UPDATE refresh_tokens SET revoked_at = NOW() WHERE token_hash = $1`, hash)
	return s.issueTokens(ctx, u, orgPtr, role)
}

func (s *Service) Logout(ctx context.Context, refreshToken, sessionID string) error {
	if sessionID != "" {
		_ = s.sessions.DeleteSession(ctx, sessionID)
	}
	if refreshToken != "" {
		hash := hashToken(refreshToken)
		_, _ = s.pool.Exec(ctx, `UPDATE refresh_tokens SET revoked_at = NOW() WHERE token_hash = $1`, hash)
	}
	return nil
}

func (s *Service) ParseAccessToken(tokenStr string) (*Claims, error) {
	token, err := jwt.ParseWithClaims(tokenStr, &Claims{}, func(t *jwt.Token) (interface{}, error) {
		if t.Method != jwt.SigningMethodHS256 {
			return nil, fmt.Errorf("unexpected signing method")
		}
		return s.secret, nil
	})
	if err != nil {
		return nil, ErrInvalidToken
	}
	claims, ok := token.Claims.(*Claims)
	if !ok || !token.Valid {
		return nil, ErrInvalidToken
	}
	return claims, nil
}

func (s *Service) ValidateSession(ctx context.Context, claims *Claims) error {
	if claims.SessionID == "" {
		return ErrSessionNotFound
	}
	sess, err := s.sessions.GetSession(ctx, claims.SessionID)
	if err != nil {
		return ErrSessionNotFound
	}
	if sess.UserID != claims.UserID {
		return ErrSessionNotFound
	}
	_ = s.sessions.RefreshSession(ctx, claims.SessionID)
	return nil
}

func (s *Service) GetUserOrgRole(ctx context.Context, userID, orgID uuid.UUID) (models.Role, error) {
	var role models.Role
	err := s.pool.QueryRow(ctx, `
		SELECT r.code FROM org_memberships om
		JOIN roles r ON r.id = om.role_id
		WHERE om.user_id = $1 AND om.org_id = $2`, userID, orgID,
	).Scan(&role)
	return role, err
}

func (s *Service) HasOrgAccess(ctx context.Context, userID, orgID uuid.UUID) (models.Role, error) {
	return s.GetUserOrgRole(ctx, userID, orgID)
}

func (s *Service) EnableTOTP(ctx context.Context, userID uuid.UUID) (secret, uri string, err error) {
	secret, uri, err = GenerateTOTPSecret("Citevision")
	if err != nil {
		return "", "", err
	}
	_, err = s.pool.Exec(ctx, `UPDATE users SET totp_secret = $1 WHERE id = $2`, secret, userID)
	return secret, uri, err
}

func (s *Service) ConfirmTOTP(ctx context.Context, userID uuid.UUID, code string) error {
	var secret *string
	err := s.pool.QueryRow(ctx, `SELECT totp_secret FROM users WHERE id = $1`, userID).Scan(&secret)
	if err != nil || secret == nil {
		return ErrInvalidTOTP
	}
	if !ValidateTOTP(*secret, code) {
		return ErrInvalidTOTP
	}
	_, err = s.pool.Exec(ctx, `UPDATE users SET totp_enabled = TRUE WHERE id = $1`, userID)
	return err
}

func (s *Service) DisableTOTP(ctx context.Context, userID uuid.UUID, code string) error {
	var secret *string
	var enabled bool
	err := s.pool.QueryRow(ctx, `SELECT totp_secret, totp_enabled FROM users WHERE id = $1`, userID).Scan(&secret, &enabled)
	if err != nil || !enabled || secret == nil {
		return ErrInvalidTOTP
	}
	if !ValidateTOTP(*secret, code) {
		return ErrInvalidTOTP
	}
	_, err = s.pool.Exec(ctx, `UPDATE users SET totp_enabled = FALSE, totp_secret = NULL WHERE id = $1`, userID)
	return err
}

type UpdateProfileRequest struct {
	FullName *string
	Email    *string
	Password *string
	Locale   *string
}

func (s *Service) UpdateProfile(ctx context.Context, userID uuid.UUID, req UpdateProfileRequest) (*models.User, error) {
	if req.FullName == nil && req.Email == nil && req.Password == nil && req.Locale == nil {
		return s.GetUserByID(ctx, userID)
	}
	q := `UPDATE users SET updated_at = NOW()`
	args := []interface{}{}
	n := 1
	if req.FullName != nil {
		q += `, full_name = $` + fmt.Sprintf("%d", n)
		args = append(args, *req.FullName)
		n++
	}
	if req.Email != nil {
		q += `, email = $` + fmt.Sprintf("%d", n)
		args = append(args, *req.Email)
		n++
	}
	if req.Locale != nil {
		q += `, locale = $` + fmt.Sprintf("%d", n)
		args = append(args, *req.Locale)
		n++
	}
	if req.Password != nil && *req.Password != "" {
		hash, err := HashPassword(*req.Password)
		if err != nil {
			return nil, err
		}
		q += `, password_hash = $` + fmt.Sprintf("%d", n)
		args = append(args, hash)
		n++
	}
	q += ` WHERE id = $` + fmt.Sprintf("%d", n)
	args = append(args, userID)
	_, err := s.pool.Exec(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	return s.GetUserByID(ctx, userID)
}
