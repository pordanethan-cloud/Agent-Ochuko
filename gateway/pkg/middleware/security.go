package middleware

import (
	"net/http"
	"strings"
)

// SecurityHeaders adds defensive HTTP security headers to every response from
// the Go Edge Gateway. These headers defend against the most common web attacks:
//
//   - Clickjacking        → X-Frame-Options / frame-ancestors CSP
//   - MIME sniffing       → X-Content-Type-Options
//   - XSS reflection      → Content-Security-Policy
//   - Info leakage        → Referrer-Policy, X-Powered-By removal
//   - Protocol downgrade  → Strict-Transport-Security (HSTS)
//   - Cross-origin leaks  → Permissions-Policy
func SecurityHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h := w.Header()

		// ── Transport Security ────────────────────────────────────────────────
		// Force HTTPS for 1 year; include subdomains; allow preload submission.
		h.Set("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")

		// ── MIME Type Sniffing ────────────────────────────────────────────────
		// Disable browser MIME guessing; honour the declared Content-Type only.
		h.Set("X-Content-Type-Options", "nosniff")

		// ── Referrer Policy ───────────────────────────────────────────────────
		// Don't leak the full URL (with JWTs/tokens in query strings) to external
		// origins. Only send origin for same-origin requests.
		h.Set("Referrer-Policy", "strict-origin-when-cross-origin")

		// ── Permissions Policy ────────────────────────────────────────────────
		// Disable all browser features that an API gateway doesn't need.
		h.Set("Permissions-Policy",
			"camera=(), microphone=(), geolocation=(), payment=(), usb=(), "+
				"interest-cohort=()")

		// ── Information Leakage Prevention ────────────────────────────────────
		// Remove the default Server header so attackers can't fingerprint the
		// stack (Go/net-http sets "Go" by default).
		h.Set("Server", "agent-ochuko-gateway")

		isHostedSite := strings.HasPrefix(r.URL.Path, "/v1/sites")

		if !isHostedSite {
			// ── Clickjacking Protection (Standard API Routes) ─────────────────
			// Prevent the API from being embedded in any iframe on an external origin.
			h.Set("X-Frame-Options", "DENY")

			// ── Content Security Policy (Strict API Gateway) ──────────────────
			h.Set("Content-Security-Policy",
				"default-src 'none'; frame-ancestors 'none'; upgrade-insecure-requests")

			// ── Cross-Origin Policies ─────────────────────────────────────────
			h.Set("Cross-Origin-Opener-Policy", "same-origin")
			h.Set("Cross-Origin-Resource-Policy", "same-origin")

			// ── Cache Control (API responses) ─────────────────────────────────
			if h.Get("Cache-Control") == "" {
				h.Set("Cache-Control", "no-store, max-age=0")
			}
		} else {
			// ── Hosted Static Site Previews (/v1/sites) ───────────────────────
			// Allow hosted sites to be framed by the Ochuko frontend and users.
			// Do NOT set X-Frame-Options DENY (which blocks all iframes unconditionally).
			h.Set("Content-Security-Policy",
				"default-src 'self' 'unsafe-inline' 'unsafe-eval' https: data: blob:; "+
					"img-src 'self' https: data: blob:; "+
					"style-src 'self' 'unsafe-inline' https:; "+
					"font-src 'self' https: data:; "+
					"frame-ancestors 'self' http://localhost:* https://*;")

			// Allow cross-origin asset loading for embedded preview iframes
			h.Set("Cross-Origin-Resource-Policy", "cross-origin")
			h.Set("Cross-Origin-Opener-Policy", "unsafe-none")
		}

		next.ServeHTTP(w, r)
	})
}
