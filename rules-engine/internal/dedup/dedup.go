package dedup

import (
	"sync"
	"time"
)

type Cache struct {
	ttl   time.Duration
	mu    sync.Mutex
	seen  map[string]time.Time
}

func NewCache(ttl time.Duration) *Cache {
	return &Cache{ttl: ttl, seen: make(map[string]time.Time)}
}

func (c *Cache) IsDuplicate(key string, now time.Time) bool {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.expire(now)
	if ts, ok := c.seen[key]; ok && now.Sub(ts) < c.ttl {
		return true
	}
	c.seen[key] = now
	return false
}

func (c *Cache) expire(now time.Time) {
	for k, ts := range c.seen {
		if now.Sub(ts) >= c.ttl {
			delete(c.seen, k)
		}
	}
}
