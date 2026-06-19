package redis

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
	goredis "github.com/redis/go-redis/v9"

	"github.com/citevision/citevision-v2/backend/internal/models"
)

type Session struct {
	UserID    uuid.UUID   `json:"user_id"`
	Email     string      `json:"email"`
	OrgID     *uuid.UUID  `json:"org_id,omitempty"`
	Role      models.Role `json:"role,omitempty"`
	CreatedAt time.Time   `json:"created_at"`
}

type Client struct {
	rdb *goredis.Client
	ttl time.Duration
}

func Connect(ctx context.Context, redisURL, password string, sessionTTL time.Duration) (*Client, error) {
	opts, err := goredis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf("parse redis url: %w", err)
	}
	if password != "" {
		opts.Password = password
	}
	rdb := goredis.NewClient(opts)
	if err := rdb.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("ping redis: %w", err)
	}
	if sessionTTL == 0 {
		sessionTTL = 7 * 24 * time.Hour
	}
	return &Client{rdb: rdb, ttl: sessionTTL}, nil
}

func (c *Client) Close() error {
	return c.rdb.Close()
}

func (c *Client) Ping(ctx context.Context) error {
	return c.rdb.Ping(ctx).Err()
}

func sessionKey(id string) string {
	return "session:" + id
}

func (c *Client) CreateSession(ctx context.Context, session Session) (string, error) {
	id := uuid.New().String()
	data, err := json.Marshal(session)
	if err != nil {
		return "", err
	}
	if err := c.rdb.Set(ctx, sessionKey(id), data, c.ttl).Err(); err != nil {
		return "", err
	}
	return id, nil
}

func (c *Client) GetSession(ctx context.Context, sessionID string) (*Session, error) {
	data, err := c.rdb.Get(ctx, sessionKey(sessionID)).Bytes()
	if err != nil {
		return nil, err
	}
	var s Session
	if err := json.Unmarshal(data, &s); err != nil {
		return nil, err
	}
	return &s, nil
}

func (c *Client) DeleteSession(ctx context.Context, sessionID string) error {
	return c.rdb.Del(ctx, sessionKey(sessionID)).Err()
}

func (c *Client) RefreshSession(ctx context.Context, sessionID string) error {
	return c.rdb.Expire(ctx, sessionKey(sessionID), c.ttl).Err()
}
