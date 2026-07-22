package proxy

import (
	"encoding/json"
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/pordanethan-cloud/agent-ochuko/gateway/pkg/auth"
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

	// Auto-cool down after 10 seconds: transition to HALF-OPEN test
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
}

func NewGatewayProxy(targetStr string, validator *auth.JWTValidator) (*GatewayProxy, error) {
	target, err := url.Parse(targetStr)
	if err != nil {
		return nil, err
	}

	cb := NewCircuitBreaker()
	rp := httputil.NewSingleHostReverseProxy(target)
	rp.FlushInterval = -1 // Immediate flushing for real-time SSE token streaming

	// Customize proxy error handler with circuit breaker integration
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

	// Intercept downstream status codes for circuit breaker telemetry
	rp.ModifyResponse = func(resp *http.Response) error {
		if resp.StatusCode >= 500 {
			cb.RecordFailure()
		} else {
			cb.RecordSuccess()
		}
		return nil
	}

	return &GatewayProxy{
		targetURL:    target,
		reverseProxy: rp,
		validator:    validator,
		circuit:      cb,
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

		// Check if endpoint requires authentication
		if isProtectedPath(r.URL.Path) && (authHeader == "" || authErr != nil) {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusUnauthorized)
			json.NewEncoder(w).Encode(map[string]string{
				"detail": "Invalid or expired authentication token.",
			})
			return
		}

		// Inject pre-validated claims into downstream headers for Python worker
		if userCtx != nil {
			r.Header.Set("X-User-Id", userCtx.UserID)
			r.Header.Set("X-User-Email", userCtx.Email)
			r.Header.Set("X-User-Role", userCtx.Role)
		}

		// Forward request to Python backend
		gp.reverseProxy.ServeHTTP(w, r)

		log.Printf("[GATEWAY] %s %s -> Proxied [%v]", r.Method, r.URL.Path, time.Since(start))
	})
}

func isProtectedPath(path string) bool {
	protectedPrefixes := []string{
		"/v1/chat",
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
