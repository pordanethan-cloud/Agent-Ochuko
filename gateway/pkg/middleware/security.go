package middleware

import "net/http"

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

		// ── Clickjacking Protection ───────────────────────────────────────────
		// Prevent the app being embedded in any iframe on an external origin.
		h.Set("X-Frame-Options", "DENY")

		// ── MIME Type Sniffing ────────────────────────────────────────────────
		// Disable browser MIME guessing; honour the declared Content-Type only.
		h.Set("X-Content-Type-Options", "nosniff")

		// ── Content Security Policy ───────────────────────────────────────────
		// Strict policy for an API gateway:
		//   - default-src 'none'   → nothing allowed unless explicitly listed
		//   - frame-ancestors 'none' → redundant with X-Frame-Options, belt+braces
		//   - upgrade-insecure-requests → force HTTP→HTTPS upgrades on mixed content
		h.Set("Content-Security-Policy",
			"default-src 'none'; frame-ancestors 'none'; upgrade-insecure-requests")

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

		// ── Cross-Origin Policies ─────────────────────────────────────────────
		// Prevent cross-origin reads of our API responses via Spectre side-channels.
		h.Set("Cross-Origin-Opener-Policy", "same-origin")
		h.Set("Cross-Origin-Resource-Policy", "same-origin")

		// ── Cache Control (API responses) ─────────────────────────────────────
		// Ensure API responses are never cached by proxies or shared caches.
		// Individual handlers can override this for specific endpoints.
		if h.Get("Cache-Control") == "" {
			h.Set("Cache-Control", "no-store, max-age=0")
		}

		next.ServeHTTP(w, r)
	})
}
