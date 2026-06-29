# app/core/jwt_validator.py
import os
import logging
import httpx
from typing import Dict, Any, Optional
from fastapi import Request, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

logger = logging.getLogger("app.core.jwt_validator")

# Bearer token extractor
security_scheme = HTTPBearer()

# Cache for JWKS keys to avoid requesting Supabase every request
_JWKS_CACHE: Optional[Dict[str, Any]] = None


async def get_jwks(supabase_url: str) -> Dict[str, Any]:
    """
    Fetches the JWKS from Supabase's well-known endpoint and caches it.
    """
    global _JWKS_CACHE
    if _JWKS_CACHE is not None:
        return _JWKS_CACHE

    jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(jwks_url)
            response.raise_for_status()
            _JWKS_CACHE = response.json()
            logger.info("Successfully fetched JWKS from Supabase.")
            return _JWKS_CACHE
    except Exception as e:
        logger.error(f"Failed to fetch JWKS from Supabase: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to initialize authentication providers."
        )


async def verify_jwt(
    request: Request = None,
    credentials: HTTPAuthorizationCredentials = Security(security_scheme)
) -> Dict[str, Any]:
    """
    Dependency to validate the Supabase JWT. Handles both symmetric (HS256)
    verification using SUPABASE_JWT_SECRET, and asymmetric (RS256) using JWKS.
    Returns the parsed token payload if valid, otherwise raises 401.
    """
    token = credentials.credentials
    supabase_url = os.getenv("SUPABASE_URL")
    jwt_secret = os.getenv("SUPABASE_JWT_SECRET")

    payload = None

    # 1. Try symmetric verification (HS256) - standard Supabase behavior
    if jwt_secret:
        try:
            # HS256 is the standard symmetric algorithm for Supabase JWTs
            payload = jwt.decode(
                token, jwt_secret, algorithms=["HS256"], options={"verify_aud": False}
            )
        except JWTError as symmetric_err:
            logger.debug(f"Symmetric verification failed: {symmetric_err}. Trying RS256/JWKS...")

    # 2. Try asymmetric verification (RS256) using JWKS
    if not payload and supabase_url:
        try:
            # Parse header to find key ID (kid)
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")
            if not kid:
                raise JWTError("Missing key ID (kid) in token header.")

            jwks = await get_jwks(supabase_url)
            signing_key = None
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    signing_key = key
                    break

            if signing_key:
                payload = jwt.decode(
                    token,
                    signing_key,
                    algorithms=["RS256", "ES256"],
                    audience="authenticated",
                    options={"verify_aud": True},
                )
        except JWTError as asymmetric_err:
            logger.error(f"Asymmetric verification failed: {asymmetric_err}")

    # If both verification flows failed, raise unauthorized
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if request:
        request.state.user = payload
    return payload


def get_auth_user(request: Request) -> Optional[Dict[str, Any]]:
    """
    Fast extraction of JWT claims without signature verification for middleware context.
    Caches the parsed payload in request.state.user to avoid double decoding.
    """
    if hasattr(request.state, "user") and request.state.user is not None:
        return request.state.user

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None

    try:
        token = auth_header.split(" ")[1]
        payload = jwt.get_unverified_claims(token)
        request.state.user = payload
        return payload
    except Exception:
        return None

