"""
log_activity — report a user action to the Bhatia Brothers Staff Portal's
central activity log (POST /api/activity).

The Python twin of logActivity.ts, for agents with a Python backend (the Lead
Gen Agent's FastAPI backend, for example). Standard library only.

COPY THIS FILE AS-IS into the agent's backend (e.g. backend/api/activity.py).
Nothing in it is app-specific; each app only needs its own two env vars in its
own .env / .env.local:

    STAFF_PORTAL_URL=https://staff.bhatiabrothers.com   # the portal's base URL
    ACTIVITY_LOG_API_KEY=bbp_...                        # this app's key

Get ACTIVITY_LOG_API_KEY from the portal at /dashboard/api-keys (admins only).
It is NOT the JWT_SECRET used for the SSO handoff -- keep them separate, and
give every app its own key. The portal works out which app sent the entry from
the key, so never send an app id.

SERVER-SIDE ONLY: the key must never reach the browser.

Fire-and-forget: log_activity() returns immediately and never raises. The
request runs on a small background thread pool; if the portal is slow, down or
rejects the entry, the user's action still succeeds and the problem is only
logged locally.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional, Union

logger = logging.getLogger("log_activity")

_TIMEOUT_SECONDS = 5
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="log-activity")
_warned_missing_config = False


def _send(url: str, api_key: str, payload: dict[str, Any]) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json", "x-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS):
            pass
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")
        logger.error("%s was rejected (%s): %s", payload["action"], err.code, detail)
    except Exception as err:  # noqa: BLE001 — logging must never break the caller
        logger.error("%s could not be sent: %s", payload["action"], err)


def log_activity(
    user_id: str,
    action: str,
    *,
    entity_type: Optional[str] = None,
    entity_id: Optional[Union[str, int]] = None,
    metadata: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """
    user_id     the signed-in user's SSO id (the `sub` from the portal's handoff token)
    action      dotted "<entity>.<verb>" name, e.g. "lead.created", "lead.status_changed"
    entity_type what was acted on, e.g. "lead"
    entity_id   its id in this app's database
    metadata    extra detail worth keeping, e.g. {"from": "new", "to": "qualified"} (max 16 KB)
    ip_address / user_agent  the end user's, from the incoming request (optional)
    """
    global _warned_missing_config

    base_url = os.environ.get("STAFF_PORTAL_URL")
    api_key = os.environ.get("ACTIVITY_LOG_API_KEY")
    if not base_url or not api_key:
        if not _warned_missing_config:
            logger.warning("STAFF_PORTAL_URL or ACTIVITY_LOG_API_KEY is not set -- activity is not being logged.")
            _warned_missing_config = True
        return

    payload: dict[str, Any] = {"userId": user_id, "action": action}
    if entity_type:
        payload["entityType"] = entity_type
    if entity_id is not None:
        payload["entityId"] = str(entity_id)
    if metadata:
        payload["metadata"] = metadata
    if ip_address:
        payload["ipAddress"] = ip_address
    if user_agent:
        payload["userAgent"] = user_agent

    try:
        _executor.submit(_send, base_url.rstrip("/") + "/api/activity", api_key, payload)
    except Exception as err:  # noqa: BLE001 — e.g. interpreter shutting down
        logger.error("%s could not be queued: %s", action, err)
