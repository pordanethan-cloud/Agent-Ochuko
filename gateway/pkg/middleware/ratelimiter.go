package middleware

import (
	"encoding/json"
	"net/http"
	"strings"
	"sync"
	"time"
)

type RateLimiter struct {
	mu           sync.Mutex
	clients      map[string]*clientBucket
	maxRequests  int
	windowLength time.Duration
}

type clientBucket struct {
	tokens     int
	lastRefill time.Time
}

func NewRateLimiter(maxRequests int, windowLength time.Duration) *RateLimiter {
	rl := &RateLimiter{
		clients:      make(map[string]*clientBucket),
		maxRequests:  maxRequests,
		windowLength: windowLength,
	}

	// Periodic cleanup of stale clients
	go func() {
		for {
			time.Sleep(5 * time.Minute)
			rl.cleanup()
		}
	}()

	return rl
}

func (rl *RateLimiter) Handler(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ip := getClientIP(r)

		if !rl.allow(ip) {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusTooManyRequests)
			json.NewEncoder(w).Encode(map[string]string{
				"detail": "Rate limit exceeded. Please wait before retrying.",
			})
			return
		}

		next.ServeHTTP(w, r)
	})
}

func (rl *RateLimiter) allow(ip string) bool {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	now := time.Now()
	bucket, exists := rl.clients[ip]
	if !exists {
		rl.clients[ip] = &clientBucket{
			tokens:     rl.maxRequests - 1,
			lastRefill: now,
		}
		return true
	}

	elapsed := now.Sub(bucket.lastRefill)
	if elapsed >= rl.windowLength {
		bucket.tokens = rl.maxRequests - 1
		bucket.lastRefill = now
		return true
	}

	if bucket.tokens > 0 {
		bucket.tokens--
		return true
	}

	return false
}

func (rl *RateLimiter) cleanup() {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	now := time.Now()
	for ip, bucket := range rl.clients {
		if now.Sub(bucket.lastRefill) > 10*time.Minute {
			delete(rl.clients, ip)
		}
	}
}

func getClientIP(r *http.Request) string {
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		parts := strings.Split(xff, ",")
		return strings.TrimSpace(parts[0])
	}
	if xri := r.Header.Get("X-Real-IP"); xri != "" {
		return xri
	}
	return r.RemoteAddr
}
