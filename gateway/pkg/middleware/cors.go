package middleware

import (
	"net/http"
	"os"
	"strings"
)

// CORSMiddleware provides high-performance edge CORS handling.
type CORSMiddleware struct {
	allowedOrigins map[string]bool
}

func NewCORSMiddleware() *CORSMiddleware {
	allowed := map[string]bool{
		"http://localhost:5173":                            true,
		"http://localhost:3000":                            true,
		"https://agentochukostore.z1.web.core.windows.net": true,
		"https://agentochukoadmin.z1.web.core.windows.net": true,
	}

	envOrigins := os.Getenv("ALLOWED_ORIGINS")
	if envOrigins != "" {
		for _, o := range strings.Split(envOrigins, ",") {
			trimmed := strings.TrimSpace(o)
			if trimmed != "" {
				allowed[trimmed] = true
			}
		}
	}

	return &CORSMiddleware{allowedOrigins: allowed}
}

func (c *CORSMiddleware) Handler(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		if origin != "" {
			if c.allowedOrigins[origin] || c.allowedOrigins["*"] {
				w.Header().Set("Access-Control-Allow-Origin", origin)
				w.Header().Set("Access-Control-Allow-Credentials", "true")
			}
		}

		if r.Method == http.MethodOptions {
			w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS, PATCH")
			w.Header().Set("Access-Control-Allow-Headers", "Authorization, Content-Type, Accept, Origin, X-Requested-With, X-Request-ID")
			w.Header().Set("Access-Control-Max-Age", "86400")
			w.WriteHeader(http.StatusNoContent)
			return
		}

		next.ServeHTTP(w, r)
	})
}
