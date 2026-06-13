"""Supabase JWT verification for RecipeSnap API routes.

Verification order:
1. Asymmetric keys (RS256/ES256) -- verified locally against the project's
   JWKS endpoint (new-style Supabase signing keys).
2. HS256 -- verified locally with SUPABASE_JWT_SECRET if that env var is set.
3. Fallback -- ask Supabase Auth directly (network call). Slower, but works
   with zero extra configuration.
"""
import os
from functools import wraps

import jwt
from flask import g, jsonify, request

_jwks_client = None


class AuthError(Exception):
    """Raised when a token is missing, invalid, or expired."""


def _get_jwks_client() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        _jwks_client = jwt.PyJWKClient(
            f"{url}/auth/v1/.well-known/jwks.json", cache_keys=True
        )
    return _jwks_client


def _verify_via_network(token: str) -> dict:
    """Validate the token by asking Supabase Auth (no local secrets needed)."""
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise AuthError("Authentication is not configured on the server.")
    try:
        res = create_client(url, key).auth.get_user(token)
    except Exception:
        raise AuthError("Invalid or expired session. Please log in again.")
    if not res or not res.user:
        raise AuthError("Invalid or expired session. Please log in again.")
    return {"sub": res.user.id, "email": res.user.email or ""}


def verify_supabase_token(token: str) -> dict:
    """Verify a Supabase access token and return its claims."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError:
        raise AuthError("Invalid session token. Please log in again.")

    alg = header.get("alg", "")
    try:
        if alg in ("RS256", "ES256"):
            signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
            return jwt.decode(
                token, signing_key.key, algorithms=[alg], audience="authenticated"
            )
        if alg == "HS256":
            secret = os.environ.get("SUPABASE_JWT_SECRET")
            if secret:
                return jwt.decode(
                    token, secret, algorithms=["HS256"], audience="authenticated"
                )
            return _verify_via_network(token)
        raise AuthError("Invalid session token. Please log in again.")
    except jwt.ExpiredSignatureError:
        raise AuthError("Your session has expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise AuthError("Invalid session token. Please log in again.")
    except AuthError:
        raise
    except Exception:
        # JWKS endpoint unreachable etc. -- fall back to asking Supabase.
        return _verify_via_network(token)


def require_user(f):
    """Decorator: require a valid Supabase session on an API route.

    Sets g.user_id and g.user_email for the request.
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Authentication required. Please log in."}), 401
        try:
            claims = verify_supabase_token(auth_header[7:].strip())
        except AuthError as e:
            return jsonify({"error": str(e)}), 401
        user_id = claims.get("sub")
        if not user_id:
            return jsonify({"error": "Invalid session token. Please log in again."}), 401
        g.user_id = user_id
        g.user_email = claims.get("email", "")
        return f(*args, **kwargs)

    return wrapper


def rate_limit_key() -> str:
    """Key rate limits by user id when a token is present, else by IP.

    The signature is NOT verified here -- this only buckets requests.
    Real authentication happens in require_user.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            payload = jwt.decode(
                auth_header[7:].strip(), options={"verify_signature": False}
            )
            sub = payload.get("sub")
            if sub:
                return f"user:{sub}"
        except Exception:
            pass
    return request.remote_addr or "anonymous"
