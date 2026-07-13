package health

import (
	"context"
)

// PingPostgres checks database connectivity.
func (c *Checker) PingPostgres(ctx context.Context) error {
	if c == nil || c.pool == nil {
		return nil
	}
	return c.pool.Ping(ctx)
}

// PingRedis checks redis connectivity.
func (c *Checker) PingRedis(ctx context.Context) error {
	if c == nil || c.redis == nil {
		return nil
	}
	return c.redis.Ping(ctx)
}
