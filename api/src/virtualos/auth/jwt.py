"""Supabase JWT verification.

Prefers the project's JWKS endpoint (ES256/RS256, new Supabase key system) and
falls back to the legacy HS256 shared secret when configured. The API verifies
the token on EVERY request (CLAUDE.md: la API valida el JWT en cada request).
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import jwt as pyjwt
from jwt import PyJWK

from virtualos.config.settings import get_settings


class AuthError(Exception):
    pass


_jwks_cache: dict[str, Any] = {"keys": None, "fetched_at": 0.0}
_JWKS_TTL_S = 3600


async def _get_jwks() -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.supabase_url:
        raise AuthError("SUPABASE_URL is not configured")
    now = time.monotonic()
    if _jwks_cache["keys"] is not None and now - _jwks_cache["fetched_at"] < _JWKS_TTL_S:
        return _jwks_cache["keys"]
    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        keys = resp.json().get("keys", [])
    _jwks_cache["keys"] = keys
    _jwks_cache["fetched_at"] = now
    return keys


async def verify_token(token: str) -> dict[str, Any]:
    """Verify a Supabase access token and return its claims. Raises AuthError."""
    settings = get_settings()
    try:
        header = pyjwt.get_unverified_header(token)
    except pyjwt.PyJWTError as exc:
        raise AuthError(f"malformed token: {exc}") from exc

    alg = header.get("alg", "")
    options = {"verify_aud": True}

    try:
        if alg == "HS256":
            if settings.supabase_jwt_secret is None:
                raise AuthError("HS256 token but SUPABASE_JWT_SECRET is not set")
            return pyjwt.decode(
                token,
                settings.supabase_jwt_secret.get_secret_value(),
                algorithms=["HS256"],
                audience="authenticated",
                options=options,
            )
        # Asymmetric: find the signing key in the project JWKS.
        kid = header.get("kid")
        keys = await _get_jwks()
        jwk = next((k for k in keys if k.get("kid") == kid), None)
        if jwk is None:
            # Key rotation: refetch once.
            _jwks_cache["keys"] = None
            keys = await _get_jwks()
            jwk = next((k for k in keys if k.get("kid") == kid), None)
        if jwk is None:
            raise AuthError("signing key not found in JWKS")
        key = PyJWK.from_dict(jwk).key
        return pyjwt.decode(token, key, algorithms=[alg], audience="authenticated", options=options)
    except AuthError:
        raise
    except pyjwt.PyJWTError as exc:
        raise AuthError(f"invalid token: {exc}") from exc
