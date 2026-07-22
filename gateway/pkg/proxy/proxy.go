package proxy

import (
	"bytes"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/pordanethan-cloud/agent-ochuko/gateway/pkg/auth"
	"github.com/pordanethan-cloud/agent-ochuko/gateway/pkg/cache"
)

// CircuitBreaker state tracking for Python AI Worker health
type CircuitBreaker struct {
	mu           sync.RWMutex
	consecutive  int32
	isOpen       bool
	lastStateMod time.Time
}

func NewCircuitBreaker() *CircuitBreaker {
	return &CircuitBreaker{
		lastStateMod: time.Now(),
	}
}

func (cb *CircuitBreaker) RecordSuccess() {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	cb.consecutive = 0
	if cb.isOpen {
		cb.isOpen = false
		log.Println("[GATEWAY-CB] Circuit Breaker reset to CLOSED. Python worker healthy.")
	}
}

func (cb *CircuitBreaker) RecordFailure() {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	cb.consecutive++
	if cb.consecutive >= 5 && !cb.isOpen {
		cb.isOpen = true
		cb.lastStateMod = time.Now()
		log.Printf("[GATEWAY-CB] Circuit Breaker TRIPPED to OPEN (%d failures). Shielding Python worker.", cb.consecutive)
	}
}

func (cb *CircuitBreaker) IsTripped() bool {
	cb.mu.RLock()
	defer cb.mu.RUnlock()

	if !cb.isOpen {
		return false
	}

	if time.Since(cb.lastStateMod) > 10*time.Second {
		return false
	}

	return true
}

type GatewayProxy struct {
	targetURL    *url.URL
	reverseProxy *httputil.ReverseProxy
	validator    *auth.JWTValidator
	circuit      *CircuitBreaker
	hotCache     *cache.HotCache
}

func NewGatewayProxy(targetStr string, validator *auth.JWTValidator, hotCache *cache.HotCache) (*GatewayProxy, error) {
	target, err := url.Parse(targetStr)
	if err != nil {
		return nil, err
	}

	cb := NewCircuitBreaker()
	rp := httputil.NewSingleHostReverseProxy(target)
	rp.FlushInterval = -1 // Immediate flushing for real-time SSE token streaming

	rp.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		log.Printf("[GATEWAY-PROXY] Connection error for %s %s: %v", r.Method, r.URL.Path, err)
		cb.RecordFailure()

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadGateway)
		json.NewEncoder(w).Encode(map[string]string{
			"detail": "Backend AI Worker unavailable or recovering.",
			"status": "degraded",
		})
	}

	rp.ModifyResponse = func(resp *http.Response) error {
		// Strip downstream CORS headers from Python to eliminate duplicate headers
		resp.Header.Del("Access-Control-Allow-Origin")
		resp.Header.Del("Access-Control-Allow-Credentials")
		resp.Header.Del("Access-Control-Allow-Methods")
		resp.Header.Del("Access-Control-Allow-Headers")
		resp.Header.Del("Access-Control-Max-Age")

		if resp.StatusCode >= 500 {
			cb.RecordFailure()
		} else {
			cb.RecordSuccess()
		}
		return nil
	}

	if hotCache == nil {
		hotCache = cache.NewHotCache(30*time.Minute, 1000)
	}

	return &GatewayProxy{
		targetURL:    target,
		reverseProxy: rp,
		validator:    validator,
		circuit:      cb,
		hotCache:     hotCache,
	}, nil
}

func (gp *GatewayProxy) Handler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()

		// 1. Check Edge Circuit Breaker State
		if gp.circuit.IsTripped() && r.URL.Path != "/health" {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusServiceUnavailable)
			json.NewEncoder(w).Encode(map[string]string{
				"detail": "Edge Circuit Breaker is active. Python worker is recovering from load.",
				"status": "circuit_open",
			})
			return
		}

		// 2. Health & Readiness direct pass-through
		if r.URL.Path == "/health" || r.URL.Path == "/ready" {
			gp.reverseProxy.ServeHTTP(w, r)
			return
		}

		// 3. JWT Verification & Context Injection
		authHeader := r.Header.Get("Authorization")
		var userCtx *auth.UserContext
		var authErr error

		if authHeader != "" {
			userCtx, authErr = gp.validator.ValidateToken(authHeader)
		}

		if isProtectedPath(r.URL.Path) && (authHeader == "" || authErr != nil) {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusUnauthorized)
			json.NewEncoder(w).Encode(map[string]string{
				"detail": "Invalid or expired authentication token.",
			})
			return
		}

		if userCtx != nil {
			r.Header.Set("X-User-Id", userCtx.UserID)
			r.Header.Set("X-User-Email", userCtx.Email)
			r.Header.Set("X-User-Role", userCtx.Role)
		}

		// 4. In-Memory Hot Cache Interception for Chat Requests
		var cacheKey string
		userID := "anonymous"
		if userCtx != nil && userCtx.UserID != "" {
			userID = userCtx.UserID
		}

		if r.Method == http.MethodPost && strings.HasPrefix(r.URL.Path, "/v1/chat") && r.Header.Get("Cache-Control") != "no-cache" {
			bodyBytes, err := io.ReadAll(r.Body)
			if err == nil && len(bodyBytes) > 0 {
				r.Body = io.NopCloser(bytes.NewBuffer(bodyBytes))
				cacheKey = cache.GenerateKey(userID, string(bodyBytes))

				if val, contentType, found := gp.hotCache.Get(cacheKey); found {
					w.Header().Set("Content-Type", contentType)
					w.Header().Set("X-Cache", "HIT")
					w.WriteHeader(http.StatusOK)
					w.Write(val)
					log.Printf("[GATEWAY-CACHE] HIT for %s [%v]", r.URL.Path, time.Since(start))
					return
				}
			}
		}

		w.Header().Set("X-Cache", "MISS")
		gp.reverseProxy.ServeHTTP(w, r)

		log.Printf("[GATEWAY] %s %s -> Proxied [%v]", r.Method, r.URL.Path, time.Since(start))
	})
}

func isProtectedPath(path string) bool {
	protectedPrefixes := []string{
		"/v1/chat",
		"/v1/responses",
		"/v1/conversations",
		"/v1/files",
		"/v1/agents",
		"/v1/admin",
		"/v1/audio",
	}
	for _, prefix := range protectedPrefixes {
		if strings.HasPrefix(path, prefix) {
			return true
		}
	}
	return false
}
