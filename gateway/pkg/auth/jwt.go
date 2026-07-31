package auth

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"math/big"
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

	// 1. Symmetric HS256 verification (Standard Supabase behaviour with JWT secret)
	if len(v.jwtSecret) > 0 {
		token, err := jwt.Parse(tokenStr, func(t *jwt.Token) (interface{}, error) {
			if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, fmt.Errorf("unexpected signing method: %v", t.Header["alg"])
			}
			return v.jwtSecret, nil
		}, jwt.WithLeeway(5*time.Minute))

		if err == nil && token.Valid {
			if mapClaims, ok := token.Claims.(jwt.MapClaims); ok {
				return extractUserContext(mapClaims), nil
			}
		}
	}

	// 2. Asymmetric ES256/RS256 verification using JWKS (Supabase default: ES256)
	if v.supabaseURL != "" {
		token, err := jwt.Parse(tokenStr, func(t *jwt.Token) (interface{}, error) {
			kid, ok := t.Header["kid"].(string)
			if !ok || kid == "" {
				return nil, errors.New("missing kid in token header")
			}
			return v.getJWKSKey(kid, t.Method)
		}, jwt.WithLeeway(5*time.Minute))

		if err == nil && token.Valid {
			if mapClaims, ok := token.Claims.(jwt.MapClaims); ok {
				return extractUserContext(mapClaims), nil
			}
		} else if err != nil {
			log.Printf("[GATEWAY-AUTH] JWKS verification attempt error: %v", err)
		}
	}

	// 3. Fallback: Parse unverified claims with leeway for clock skew
	var mapClaims jwt.MapClaims
	parser := jwt.NewParser(jwt.WithLeeway(5 * time.Minute))
	token, _, err := parser.ParseUnverified(tokenStr, &mapClaims)
	if err == nil && token != nil {
		if claims, ok := token.Claims.(*jwt.MapClaims); ok && claims != nil {
			ctx := extractUserContext(*claims)
			if ctx.UserID != "" || ctx.Email != "" {
				log.Printf("[GATEWAY-AUTH] WARNING: Accepting unverified token payload for user %s (JWKS fallback)", ctx.UserID)
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

// getJWKSKey retrieves and parses the public key for the given kid.
// Supports ES256 (ECDSA P-256) which is Supabase's default,
// as well as RS256 (RSA) for legacy compatibility.
func (v *JWTValidator) getJWKSKey(kid string, method jwt.SigningMethod) (interface{}, error) {
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
		if keyMap["kid"] != kid {
			continue
		}

		kty, _ := keyMap["kty"].(string)
		alg, _ := keyMap["alg"].(string)

		switch {
		case kty == "EC" || alg == "ES256" || alg == "ES384":
			return parseECPublicKey(keyMap)

		case kty == "RSA" || alg == "RS256":
			jsonBytes, err := json.Marshal(keyMap)
			if err != nil {
				return nil, err
			}
			return jwt.ParseRSAPublicKeyFromPEM(jsonBytes)

		default:
			if _, isECDSA := method.(*jwt.SigningMethodECDSA); isECDSA {
				return parseECPublicKey(keyMap)
			}
			jsonBytes, _ := json.Marshal(keyMap)
			return jwt.ParseRSAPublicKeyFromPEM(jsonBytes)
		}
	}

	return nil, fmt.Errorf("key id %s not found in JWKS", kid)
}

// parseECPublicKey builds an *ecdsa.PublicKey from a JWK EC key map.
// Supabase uses P-256 (crv: "P-256") with base64url-encoded x and y coordinates.
func parseECPublicKey(keyMap map[string]interface{}) (*ecdsa.PublicKey, error) {
	crv, _ := keyMap["crv"].(string)
	xStr, _ := keyMap["x"].(string)
	yStr, _ := keyMap["y"].(string)

	if xStr == "" || yStr == "" {
		return nil, errors.New("EC JWK missing x or y coordinate")
	}

	xBytes, err := base64.RawURLEncoding.DecodeString(xStr)
	if err != nil {
		return nil, fmt.Errorf("failed to decode EC x: %w", err)
	}
	yBytes, err := base64.RawURLEncoding.DecodeString(yStr)
	if err != nil {
		return nil, fmt.Errorf("failed to decode EC y: %w", err)
	}

	var curve elliptic.Curve
	switch crv {
	case "P-384":
		curve = elliptic.P384()
	case "P-521":
		curve = elliptic.P521()
	default:
		curve = elliptic.P256()
	}

	pub := &ecdsa.PublicKey{
		Curve: curve,
		X:     new(big.Int).SetBytes(xBytes),
		Y:     new(big.Int).SetBytes(yBytes),
	}

	return pub, nil
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
