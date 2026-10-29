"""
Staff Portal access control, end to end inside this app: the real FastAPI app,
real session cookies and the real access.py helper, talking over HTTP to a
stand-in for the portal's GET /api/authz/permissions.

    .\\venv\\Scripts\\python.exe -m unittest backend.test_access_control -v
"""

import json
import os
import threading
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import jwt
from fastapi.testclient import TestClient

from backend.api.routes import access
from backend.main import app  # loads .env.local; the test values below are set afterwards
from backend.services import database

API_KEY = "bbp_test-key"
HANDOFF_SECRET = "test-handoff-secret"
SESSION_SECRET = "test-session-secret"

LEAD_USER = ["leads.export", "leads.generate", "leads.save", "outreach.send_email"]

# What the portal would answer, per username. Tests change it to simulate revocation.
PORTAL_ANSWERS: dict = {}
PORTAL_CALLS: list = []


class FakePortal(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep test output quiet
        pass

    def _send(self, status: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path != "/api/authz/permissions" or self.headers.get("x-api-key") != API_KEY:
            return self._send(401, {"error": "Missing or invalid API key."})
        username = parse_qs(url.query).get("username", [""])[0]
        PORTAL_CALLS.append(username)
        answer = PORTAL_ANSWERS.get(username, {"allowed": False, "reason": "unknown_user"})
        self._send(200, {"application": "LGA", "roles": [], "permissions": [], "maxAgeSeconds": 60, "reason": None, **answer})

    def do_POST(self):  # activity log entries
        self.rfile.read(int(self.headers.get("content-length", 0)))
        self._send(201, {"id": "x"})


def session_cookie(username: str) -> str:
    claims = {"sub": username, "name": username.upper(), "role": "staff", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    return jwt.encode(claims, SESSION_SECRET, algorithm="HS256")


def handoff_token(username: str, **overrides) -> str:
    """A token like the portal's; an override of None leaves that claim out."""
    now = datetime.now(timezone.utc)
    claims = {
        "sub": username,
        "name": username.upper(),
        "role": "staff",
        "iss": "bb-staff-portal",
        "aud": "lead-gen-agent",
        "iat": now,
        "exp": now + timedelta(seconds=60),
        "jti": uuid.uuid4().hex,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, HANDOFF_SECRET, algorithm="HS256")


class AccessControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakePortal)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.saved_env = {k: os.environ.get(k) for k in ("STAFF_PORTAL_URL", "ACTIVITY_LOG_API_KEY", "JWT_SECRET", "SESSION_SECRET")}
        os.environ.update({
            "STAFF_PORTAL_URL": f"http://127.0.0.1:{cls.server.server_port}",
            "ACTIVITY_LOG_API_KEY": API_KEY,
            "JWT_SECRET": HANDOFF_SECRET,
            "SESSION_SECRET": SESSION_SECRET,
        })

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        for key, value in cls.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def setUp(self):
        access._cache.clear()
        PORTAL_CALLS.clear()
        PORTAL_ANSWERS.clear()
        PORTAL_ANSWERS.update({
            "u001": {"allowed": False, "reason": "access_disabled"},  # Job Card only
            "u002": {"allowed": True, "roles": [{"key": "lead_user", "name": "Lead User"}], "permissions": LEAD_USER},
        })
        # No real database: routes that get past the access check read nothing.
        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=[])
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        pool_patch = patch.object(database, "get_pool", AsyncMock(return_value=pool))
        pool_patch.start()
        self.addCleanup(pool_patch.stop)
        self.client = TestClient(app)  # no `with`: the startup DB pool isn't needed

    def as_user(self, username: str):
        self.client.cookies.set("lga_session", session_cookie(username))

    def test_no_session_is_401(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.client.get("/api/email-templates").status_code, 401)
        self.assertEqual(self.client.post("/api/save-leads", json={"leads": []}).status_code, 401)

    def test_user_without_lead_gen_access_is_refused_everywhere(self):
        self.as_user("u001")
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 403)
        self.assertEqual(me.json()["reason"], "access_disabled")
        self.assertIn("lga_session", me.headers.get("set-cookie", ""))  # cookie cleared
        self.as_user("u001")
        self.assertEqual(self.client.get("/api/product-service-types").status_code, 403)
        self.assertEqual(self.client.post("/api/save-leads", json={"leads": []}).status_code, 403)

    def test_sso_handoff_is_refused_without_access(self):
        self.assertEqual(self.client.post("/api/auth/sso", json={"token": handoff_token("u001")}).status_code, 403)
        ok = self.client.post("/api/auth/sso", json={"token": handoff_token("u002")})
        self.assertEqual(ok.status_code, 200)
        self.assertIn("lga_session", ok.headers.get("set-cookie", ""))

    def test_handoff_token_must_be_for_this_app_from_the_portal_and_unused(self):
        def sso(token):
            return self.client.post("/api/auth/sso", json={"token": token}).status_code

        self.assertEqual(sso(handoff_token("u002", aud="job-card-agent")), 401)
        self.assertEqual(sso(handoff_token("u002", aud=None)), 401)
        self.assertEqual(sso(handoff_token("u002", iss="someone-else")), 401)
        self.assertEqual(sso(handoff_token("u002", jti=None)), 401)
        self.assertEqual(sso(handoff_token("u002", exp=datetime.now(timezone.utc) - timedelta(seconds=30))), 401)
        claims = jwt.decode(handoff_token("u002"), options={"verify_signature": False})
        self.assertEqual(sso(jwt.encode(claims, "wrong-secret", algorithm="HS256")), 401)
        self.assertEqual(sso(jwt.encode(claims, None, algorithm="none")), 401)

        token = handoff_token("u002")
        self.assertEqual(sso(token), 200)
        self.assertEqual(sso(token), 401)  # replayed

    def test_session_cookie_flags(self):
        from backend.api.routes import auth as auth_routes

        ok = self.client.post("/api/auth/sso", json={"token": handoff_token("u002")})
        cookie = ok.headers.get("set-cookie", "").lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=lax", cookie)
        self.assertNotIn("secure", cookie)  # the fake portal is plain http
        with patch.dict(os.environ, {"STAFF_PORTAL_URL": "https://portal.example"}):
            self.assertTrue(auth_routes._cookie_kwargs()["secure"])
        with patch.dict(os.environ, {"SESSION_COOKIE_SAMESITE": "none", "SESSION_COOKIE_SECURE": "false"}):
            self.assertEqual(auth_routes._cookie_kwargs()["samesite"], "none")
            self.assertTrue(auth_routes._cookie_kwargs()["secure"])

    def test_lead_user_gets_only_lead_user_features(self):
        self.as_user("u002")
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["roles"], ["lead_user"])
        self.assertEqual(me.json()["permissions"], LEAD_USER)

        # Allowed: gets past the check (the mocked database answers).
        self.assertEqual(self.client.get("/api/product-service-types").status_code, 200)
        self.assertEqual(self.client.get("/api/email-templates").status_code, 200)
        # Not part of Lead User.
        self.assertEqual(self.client.post("/api/test-smtp").status_code, 403)
        self.assertEqual(self.client.delete("/api/email-templates/1").status_code, 403)
        self.assertEqual(
            self.client.post("/api/email-templates", json={"template_name": "x", "subject": "s", "body": "b"}).status_code,
            403,
        )
        bulk = self.client.post("/api/send-bulk-email", json={"subject": "s", "body": "b", "leadIds": [], "leads": []})
        self.assertEqual(bulk.status_code, 403)

    def test_revocation_reaches_fresh_checks_at_once_and_everything_within_a_minute(self):
        self.as_user("u002")
        self.assertEqual(self.client.get("/api/email-templates").status_code, 200)

        PORTAL_ANSWERS["u002"] = {"allowed": False, "reason": "account_suspended"}
        # Page loads and sensitive actions ask the portal fresh: refused straight away.
        self.assertEqual(self.client.get("/api/auth/me").status_code, 403)
        # Other routes may use the cached answer for up to 60 seconds, then refuse.
        self.as_user("u002")
        with patch.object(access.time, "monotonic", return_value=access.time.monotonic() + 61):
            self.assertEqual(self.client.get("/api/email-templates").status_code, 403)

    def test_portal_unreachable_means_no_access(self):
        self.as_user("u002")
        with patch.dict(os.environ, {"STAFF_PORTAL_URL": "http://127.0.0.1:9"}):
            self.assertEqual(self.client.get("/api/auth/me").status_code, 403)
            self.assertEqual(self.client.get("/api/email-templates").status_code, 403)

    def test_wrong_api_key_means_no_access(self):
        self.as_user("u002")
        with patch.dict(os.environ, {"ACTIVITY_LOG_API_KEY": "bbp_wrong"}):
            self.assertEqual(self.client.get("/api/auth/me").status_code, 403)


if __name__ == "__main__":
    unittest.main()
