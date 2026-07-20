package middleware

import (
	"net"
	"net/http"
	"sync"
	"time"
)

// tokenBucket is a simple per-key token bucket (no external deps).
type tokenBucket struct {
	tokens   float64
	last     time.Time
	rate     float64 // tokens per second
	capacity float64
}

// RateLimiter holds buckets keyed by client IP and prunes idle entries.
type RateLimiter struct {
	mu       sync.Mutex
	buckets  map[string]*tokenBucket
	rate     float64
	capacity float64
	lastGC   time.Time
}

// NewRateLimiter builds a limiter allowing `burst` requests immediately and
// refilling at `perMinute` requests/minute thereafter.
func NewRateLimiter(perMinute int, burst int) *RateLimiter {
	if perMinute < 1 {
		perMinute = 60
	}
	if burst < 1 {
		burst = perMinute
	}
	return &RateLimiter{
		buckets:  make(map[string]*tokenBucket),
		rate:     float64(perMinute) / 60.0,
		capacity: float64(burst),
		lastGC:   time.Now(),
	}
}

func (rl *RateLimiter) allow(key string) bool {
	rl.mu.Lock()
	defer rl.mu.Unlock()
	now := time.Now()

	// Opportunistic GC of idle buckets to bound memory.
	if now.Sub(rl.lastGC) > 5*time.Minute {
		for k, b := range rl.buckets {
			if now.Sub(b.last) > 10*time.Minute {
				delete(rl.buckets, k)
			}
		}
		rl.lastGC = now
	}

	b, ok := rl.buckets[key]
	if !ok {
		b = &tokenBucket{tokens: rl.capacity, last: now, rate: rl.rate, capacity: rl.capacity}
		rl.buckets[key] = b
	}
	// Refill.
	elapsed := now.Sub(b.last).Seconds()
	b.tokens += elapsed * b.rate
	if b.tokens > b.capacity {
		b.tokens = b.capacity
	}
	b.last = now
	if b.tokens < 1 {
		return false
	}
	b.tokens--
	return true
}

// Middleware returns an http middleware enforcing the limit per client IP.
func (rl *RateLimiter) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !rl.allow(clientIP(r)) {
			w.Header().Set("Retry-After", "60")
			http.Error(w, `{"error":"rate limit exceeded"}`, http.StatusTooManyRequests)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func clientIP(r *http.Request) string {
	// chi RealIP already normalizes RemoteAddr from X-Forwarded-For/X-Real-IP.
	if host, _, err := net.SplitHostPort(r.RemoteAddr); err == nil {
		return host
	}
	return r.RemoteAddr
}
