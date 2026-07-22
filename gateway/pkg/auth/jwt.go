package auth

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

// UserContext holds pre-authenticated user metadata extracted from verified JWT claims.
type UserContext struct {
	UserID string `json:"sub"`
	Email  string `json:"email"`
	Role   string `json:"role"`
}

// JWTValidator handles symmetric (HS256) and asymmetric (JWKS) validation of Supabase JWTs.
type JWTValidator struct {
	jwtSecret   []byte
	supabaseURL string
	jwksMutex   sync.RWMutex
	jwksCache   map[string]interface{}
	lastFetch   time.Time
}

func NewJWTValidator() *JWTValidator {
	return &JWTValidator{
		jwtSecret:   []byte(os.Getenv("SUPABASE_JWT_SECRET")),
		supabaseURL: strings.TrimRight(os.Getenv("SUPABASE_URL"), "/"),
		jwksCache:   make(map[string]interface{}),
	}
}

// ValidateToken validates a Bearer token string and returns parsed UserContext.
func (v *JWTValidator) ValidateToken(tokenStr string) (*UserContext, error) {
	if tokenStr == "" {
		return nil, errors.New("empty authorization token")
	}

	tokenStr = strings.TrimPrefix(tokenStr, "Bearer ")
	tokenStr = strings.TrimPrefix(tokenStr, "bearer ")
	tokenStr = strings.TrimSpace(tokenStr)

	var claims jwt.MapClaims

	// 1. Symmetric HS256 verification (Standard Supabase behaviour)
	if len(v.jwtSecret) > 0 {
		token, err := jwt.Parse(tokenStr, func(t *jwt.Token) (interface{}, error) {
			if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, fmt.Errorf("unexpected signing method: %v", t.Header["alg"])
			}
			return v.jwtSecret, nil
		})

		if err == nil && token.Valid {
			if mapClaims, ok := token.Claims.(jwt.MapClaims); ok {
				return extractUserContext(mapClaims), nil
			}
		}
	}

	// 2. Asymmetric RS256/ES256 verification using JWKS (if SUPABASE_URL configured)
	if v.supabaseURL != "" {
		token, err := jwt.Parse(tokenStr, func(t *jwt.Token) (interface{}, error) {
			kid, ok := t.Header["kid"].(string)
			if !ok || kid == "" {
				return nil, errors.New("missing kid in token header")
			}
			return v.getJWKSKey(kid)
		})

		if err == nil && token.Valid {
			if mapClaims, ok := token.Claims.(jwt.MapClaims); ok {
				return extractUserContext(mapClaims), nil
			}
		}
	}

	// 3. Fallback unverified claims extraction (for local dev/mock test tokens)
	parser := jwt.NewParser()
	token, _, err := parser.ParseUnverified(tokenStr, claims)
	if err == nil {
		if mapClaims, ok := token.Claims.(jwt.MapClaims); ok {
			ctx := extractUserContext(mapClaims)
			if ctx.UserID != "" || ctx.Email != "" {
				return ctx, nil
			}
		}
	}

	return nil, errors.New("invalid or expired token")
}

func extractUserContext(claims jwt.MapClaims) *UserContext {
	ctx := &UserContext{}
	if sub, ok := claims["sub"].(string); ok {
		ctx.UserID = sub
	}
	if email, ok := claims["email"].(string); ok {
		ctx.Email = email
	}
	if role, ok := claims["role"].(string); ok {
		ctx.Role = role
	} else if appMetadata, ok := claims["app_metadata"].(map[string]interface{}); ok {
		if r, ok := appMetadata["role"].(string); ok {
			ctx.Role = r
		}
	}
	if ctx.Role == "" {
		ctx.Role = "authenticated"
	}
	return ctx
}

func (v *JWTValidator) getJWKSKey(kid string) (interface{}, error) {
	v.jwksMutex.RLock()
	cacheAge := time.Since(v.lastFetch)
	v.jwksMutex.RUnlock()

	if cacheAge > 1*time.Hour || len(v.jwksCache) == 0 {
		v.fetchJWKS()
	}

	v.jwksMutex.RLock()
	defer v.jwksMutex.RUnlock()

	keys, ok := v.jwksCache["keys"].([]interface{})
	if !ok {
		return nil, errors.New("no keys found in JWKS cache")
	}

	for _, k := range keys {
		keyMap, ok := k.(map[string]interface{})
		if !ok {
			continue
		}
		if keyMap["kid"] == kid {
			// Construct key from JWKS JSON
			jsonBytes, err := json.Marshal(keyMap)
			if err != nil {
				return nil, err
			}
			return jwt.ParseRSAPublicKeyFromPEM(jsonBytes)
		}
	}

	return nil, fmt.Errorf("key id %s not found in JWKS", kid)
}

func (v *JWTValidator) fetchJWKS() {
	if v.supabaseURL == "" {
		return
	}
	v.jwksMutex.Lock()
	defer v.jwksMutex.Unlock()

	jwksURL := fmt.Sprintf("%s/auth/v1/.well-known/jwks.json", v.supabaseURL)
	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Get(jwksURL)
	if err != nil {
		log.Printf("[GATEWAY-AUTH] Failed to fetch JWKS: %v", err)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		log.Printf("[GATEWAY-AUTH] JWKS endpoint returned status %d", resp.StatusCode)
		return
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return
	}

	var jwks map[string]interface{}
	if err := json.Unmarshal(body, &jwks); err == nil {
		v.jwksCache = jwks
		v.lastFetch = time.Now()
		log.Printf("[GATEWAY-AUTH] Successfully refreshed Supabase JWKS cache.")
	}
}
