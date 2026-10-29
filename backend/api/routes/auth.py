"""
Cross-app SSO: this agent trusts the Bhatia Brothers Staff Portal's login
instead of running its own. See the portal's src/lib/sso.ts for the full
handoff flow; this module is steps 2+ of it:

  1. (In the portal) the user clicks this app's tile. The portal mints a
     SHORT-LIVED (60s) JWT signed with the shared JWT_SECRET and redirects
     the browser to this app's /auth/sso?token=... (a client-side route,
     see src/auth/SsoHandler.tsx — there's no server template to render it
     from, so the SPA shell handles that path itself).
  2. SsoHandler POSTs that token to /api/auth/sso (this file). We verify it
     was really signed by the portal, then mint OUR OWN longer-lived session
     and hand it back as an httpOnly cookie (lga_session).
  3. Every other page load calls /api/auth/me to read who's signed in, and
     /api/auth/logout clears the cookie when the user signs out of the
     portal (it calls this across origins with credentials included).

Access itself lives in the portal's database: who may use this app and with
which permissions. Both the handoff and /api/auth/me ask the portal live
(access.py), and every API route checks its own permission (see leads.py),
so revoking someone in the portal takes effect here within a minute.
"""

import os
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from backend.api.routes.access import check_access

logger = logging.getLogger(__name__)
router = APIRouter()

SESSION_COOKIE_NAME = "lga_session"
SESSION_MAX_AGE_SECONDS = 8 * 60 * 60  # 8 hours

# Must match the portal's src/lib/sso.ts (SSO_ISSUER and the LGA audience).
HANDOFF_ISSUER = "bb-staff-portal"
HANDOFF_AUDIENCE = "lead-gen-agent"

# jti -> expiry (epoch seconds) of handoff tokens already exchanged, so each
# one works once. In memory: with several worker processes or instances, a
# token could be replayed once per process within its 60 seconds; use a
# shared store (e.g. Redis or a database table) for such deployments.
_used_handoffs: dict = {}
_used_handoffs_lock = threading.Lock()


def _claim_handoff(jti: str, exp: float) -> bool:
    """True the first time `jti` is seen; False if it was already used."""
    now = time.time()
    with _used_handoffs_lock:
        for key in [k for k, until in _used_handoffs.items() if until < now]:
            del _used_handoffs[key]
        if jti in _used_handoffs:
            return False
        _used_handoffs[jti] = exp
        return True


def _handoff_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET is not configured")
    return secret


def _session_secret() -> str:
    # Deliberately separate from JWT_SECRET: whoever can mint handoff tokens
    # (the portal) must not also be able to forge this app's sessions.
    secret = os.getenv("SESSION_SECRET")
    if not secret:
        raise RuntimeError("SESSION_SECRET is not configured")
    return secret


def _cookie_kwargs() -> dict:
    # localhost:5173 <-> localhost:3000 are "same-site" (site is scheme +
    # registrable domain, not port), so SameSite=Lax over plain http works
    # for local dev. A real cross-domain deployment (e.g. portal.example.com
    # vs agent.example.com) needs samesite="none", secure=True, and HTTPS on
    # both apps, or the browser will silently refuse to set/send the cookie.
    # Secure defaults on whenever the portal runs on HTTPS; override with
    # SESSION_COOKIE_SECURE=true/false. SESSION_COOKIE_SAMESITE=none (for
    # cross-domain deployments) always forces Secure.
    portal = os.getenv("STAFF_PORTAL_URL") or os.getenv("PORTAL_URL") or ""
    secure_env = os.getenv("SESSION_COOKIE_SECURE", "").strip().lower()
    secure = secure_env == "true" if secure_env in ("true", "false") else portal.startswith("https://")
    samesite = os.getenv("SESSION_COOKIE_SAMESITE", "lax").strip().lower()
    if samesite not in ("lax", "strict", "none"):
        samesite = "lax"
    if samesite == "none":
        secure = True
    return {"httponly": True, "samesite": samesite, "secure": secure, "path": "/"}


def session_user_id(request: Request) -> Optional[str]:
    """
    The signed-in user's portal id (the handoff token's `sub`), read from the
    lga_session cookie, or None if there's no valid session. Used to attribute
    actions in the Staff Portal's activity log. The frontend has to send its
    API calls with `credentials: "include"` for the cookie to arrive here.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    try:
        claims = jwt.decode(token, _session_secret(), algorithms=["HS256"])
    except (jwt.PyJWTError, RuntimeError):
        return None
    sub = claims.get("sub")
    return sub if isinstance(sub, str) and sub else None


def current_username(request: Request) -> Optional[str]:
    """The SSO user for access.py's require_permission (same as session_user_id)."""
    return session_user_id(request)


def _no_access(reason: Optional[str]) -> JSONResponse:
    """403 that also clears this app's session, so a revoked user is signed out here."""
    response = JSONResponse(status_code=403, content={"detail": "No access to Lead Gen Agent", "reason": reason})
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response


@router.post("/api/auth/sso")
async def sso_exchange(request: Request, response: Response):
    body = await request.json()
    token = body.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="Missing token")

    if not isinstance(token, str) or len(token) > 8192:
        raise HTTPException(status_code=400, detail="Missing token")

    try:
        claims = jwt.decode(
            token,
            _handoff_secret(),
            algorithms=["HS256"],
            audience=HANDOFF_AUDIENCE,
            issuer=HANDOFF_ISSUER,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "jti"]},
            leeway=5,
        )
    except jwt.PyJWTError as exc:
        # The reason only, never the token itself.
        logger.warning(f"Rejected SSO handoff token: {type(exc).__name__}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    sub = claims.get("sub")
    jti = claims.get("jti")
    if not isinstance(sub, str) or not sub or not isinstance(jti, str) or not jti:
        raise HTTPException(status_code=401, detail="Invalid token")
    if not _claim_handoff(jti, float(claims["exp"]) + 5):
        logger.warning("Rejected a reused SSO handoff token")
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    # The portal only mints a token for people with access, but check again
    # live: access may have been revoked in the seconds since.
    access = check_access(sub, fresh=True)
    if not access.allowed:
        return _no_access(access.reason)

    name = claims.get("name")
    role = claims.get("role", "staff")
    session_claims = {
        "sub": claims.get("sub"),
        "name": name,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=SESSION_MAX_AGE_SECONDS),
    }
    session_token = jwt.encode(session_claims, _session_secret(), algorithm="HS256")

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        **_cookie_kwargs(),
    )
    return {"name": name, "role": role}


@router.get("/api/auth/me")
async def auth_me(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not signed in")
    try:
        claims = jwt.decode(token, _session_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Session expired")

    # Roles and permissions come live from the portal, so the UI only shows
    # what this person may do right now. The API routes check again anyway.
    access = check_access(claims.get("sub") or "", fresh=True)
    if not access.allowed:
        return _no_access(access.reason)
    return {
        "name": claims.get("name"),
        "role": claims.get("role", "staff"),
        "roles": list(access.roles),
        "permissions": sorted(access.permissions),
    }


@router.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"success": True}
