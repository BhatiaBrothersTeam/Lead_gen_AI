"""
check_access -- ask the Bhatia Brothers Staff Portal whether the signed-in
person may use THIS app right now, and with which permissions
(GET /api/authz/permissions).

The Python twin of checkAccess.ts, for agents with a Python backend (the Lead
Gen Agent's FastAPI backend, for example). Standard library only.

COPY THIS FILE AS-IS into the agent's backend, next to its SSO auth module
(e.g. backend/api/routes/access.py beside backend/api/routes/auth.py).
It uses the SAME two env vars as log_activity.py -- the app's portal API key
identifies the app, so an agent can only ever ask about itself:

    STAFF_PORTAL_URL=https://staff.bhatiabrothers.com
    ACTIVITY_LOG_API_KEY=bbp_...

SERVER-SIDE ONLY. Fails closed: if the portal can't be reached, the answer is
"no access", never a stale or guessed "yes".

Answers are cached in memory for at most the portal's maxAgeSeconds (60s), so
revoking access or suspending an account takes effect here within a minute.
Pass fresh=True for sensitive actions (bulk email, approvals) to skip the cache.

FastAPI usage:

    from fastapi import Depends
    from .access import require_permission

    @router.post("/api/generate-leads")
    async def generate_leads(input_data: GenerateLeadsInput,
                             user=Depends(require_permission("leads.generate"))):
        ...

`require_permission` needs a `current_username(request)` function in the
sibling auth module that returns the SSO user's `sub` from the agent's own
session, or None (see the README).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger("check_access")

_TIMEOUT_SECONDS = 5
_MAX_CACHE_SECONDS = 60
_cache: dict[str, tuple[float, "Access"]] = {}
_lock = threading.Lock()


@dataclass(frozen=True)
class Access:
    allowed: bool
    reason: Optional[str] = None
    roles: tuple[str, ...] = field(default_factory=tuple)
    permissions: frozenset[str] = field(default_factory=frozenset)

    def can(self, permission: str) -> bool:
        return self.allowed and permission in self.permissions


_DENIED_UNAVAILABLE = Access(allowed=False, reason="portal_unavailable")


def _fetch(username: str) -> tuple[Access, float]:
    base_url = os.environ.get("STAFF_PORTAL_URL")
    api_key = os.environ.get("ACTIVITY_LOG_API_KEY")
    if not base_url or not api_key:
        logger.error("STAFF_PORTAL_URL or ACTIVITY_LOG_API_KEY is not set -- denying access.")
        return _DENIED_UNAVAILABLE, 0

    query = urllib.parse.urlencode({"username": username})
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/authz/permissions?{query}",
        headers={"x-api-key": api_key},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as res:
            body = json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        logger.error("access check for %s was refused (%s)", username, err.code)
        return _DENIED_UNAVAILABLE, 0
    except Exception as err:  # noqa: BLE001 -- any failure means "no"
        logger.error("access check for %s failed: %s", username, err)
        return _DENIED_UNAVAILABLE, 0

    access = Access(
        allowed=body.get("allowed") is True,
        reason=body.get("reason"),
        roles=tuple(r["key"] for r in body.get("roles", []) if isinstance(r, dict) and "key" in r),
        permissions=frozenset(p for p in body.get("permissions", []) if isinstance(p, str)),
    )
    max_age = min(float(body.get("maxAgeSeconds", _MAX_CACHE_SECONDS)), _MAX_CACHE_SECONDS)
    return access, max_age


def check_access(username: str, *, fresh: bool = False) -> Access:
    """The person's current access to this app. `username` is the SSO token's `sub`."""
    key = username.lower()
    now = time.monotonic()
    if not fresh:
        with _lock:
            hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
    access, max_age = _fetch(key)
    if max_age > 0:
        with _lock:
            _cache[key] = (now + max_age, access)
    return access


def require_permission(permission: str, *, fresh: bool = False) -> Callable:
    """FastAPI dependency: 401 without a session, 403 without the permission."""
    from fastapi import Depends, HTTPException  # imported here so the module works without FastAPI

    from .auth import current_username  # the agent's own SSO-session reader; adjust the import

    def dependency(username: Optional[str] = Depends(current_username)) -> Access:
        if not username:
            raise HTTPException(status_code=401, detail="Sign in through the Staff Portal.")
        access = check_access(username, fresh=fresh)
        if not access.can(permission):
            raise HTTPException(status_code=403, detail="You don't have permission to do this.")
        return access

    return dependency
