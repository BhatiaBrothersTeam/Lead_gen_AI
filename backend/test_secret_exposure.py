"""
The routes that use server-side secrets (AI provider keys, SMTP credentials)
sit behind the Staff Portal access check, and email routes fail clearly when
SMTP isn't configured instead of falling back to built-in credentials.

    .\\venv\\Scripts\\python.exe -m unittest backend.test_secret_exposure -v
"""

import os
import unittest
from unittest.mock import AsyncMock, patch

from backend.api.routes import leads as leads_routes
from backend.services import email_service
# Imported as a module so unittest doesn't collect (and rerun) its test class here.
from backend import test_access_control as access_tests
from backend.test_access_control import PORTAL_ANSWERS

SMTP_VARS = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM")
GENERATE = {"productName": "Air compressor", "brand": "Atlas", "division": "ISD", "description": "x"}


def without_smtp():
    """Environment with no SMTP settings at all (restored afterwards)."""
    env = patch.dict(os.environ)
    env.start()
    for key in SMTP_VARS:
        os.environ.pop(key, None)
    return env


class SecretRouteTests(unittest.TestCase):
    # Same fake portal, session cookies and mocked database as the access tests.
    setUpClass = classmethod(access_tests.AccessControlTests.setUpClass.__func__)
    tearDownClass = classmethod(access_tests.AccessControlTests.tearDownClass.__func__)
    setUp = access_tests.AccessControlTests.setUp
    as_user = access_tests.AccessControlTests.as_user

    def grant(self, username: str, *permissions: str):
        PORTAL_ANSWERS[username] = {"allowed": True, "roles": [], "permissions": list(permissions)}
        self.as_user(username)

    # --- AI lead generation: the only path to the provider keys -------------

    def test_generate_leads_needs_a_session(self):
        self.assertEqual(self.client.post("/api/generate-leads", json=GENERATE).status_code, 401)

    def test_generate_leads_needs_the_permission(self):
        self.as_user("u001")  # no Lead Gen access at all
        self.assertEqual(self.client.post("/api/generate-leads", json=GENERATE).status_code, 403)
        self.grant("u003", "leads.save", "outreach.send_email")  # Lead Gen access, but not this
        self.assertEqual(self.client.post("/api/generate-leads", json=GENERATE).status_code, 403)

    def test_generate_leads_with_the_permission_reaches_the_pipeline(self):
        self.grant("u004", "leads.generate")
        analyze = AsyncMock(side_effect=RuntimeError("provider not called in tests"))
        with patch.object(leads_routes, "analyze_product", analyze):
            res = self.client.post("/api/generate-leads", json=GENERATE)
        self.assertEqual(res.status_code, 200)
        analyze.assert_awaited_once()

    # --- Email: no built-in SMTP credentials --------------------------------

    def test_email_routes_need_a_session_and_permission_before_smtp(self):
        env = without_smtp()
        self.addCleanup(env.stop)
        self.assertEqual(self.client.post("/api/test-smtp").status_code, 401)
        self.assertEqual(self.client.post("/api/send-email", json={"email": "a@b.co", "subject": "s", "body": "b"}).status_code, 401)
        self.grant("u005", "leads.generate")
        self.assertEqual(self.client.post("/api/test-smtp").status_code, 403)
        self.assertEqual(self.client.post("/api/send-email", json={"email": "a@b.co", "subject": "s", "body": "b"}).status_code, 403)

    def test_email_routes_are_503_without_smtp_settings(self):
        env = without_smtp()
        self.addCleanup(env.stop)
        self.grant("u006", "outreach.test_smtp", "outreach.send_email", "outreach.send_bulk")
        with patch.object(email_service.smtplib, "SMTP") as smtp:
            test = self.client.post("/api/test-smtp")
            single = self.client.post("/api/send-email", json={"email": "a@b.co", "subject": "s", "body": "b"})
            bulk = self.client.post("/api/send-bulk-email", json={"subject": "s", "body": "b", "leads": [{"email": "a@b.co"}]})
        for res in (test, single, bulk):
            self.assertEqual(res.status_code, 503)
            self.assertEqual(res.json()["detail"], "SMTP not configured")
        smtp.assert_not_called()


class SmtpSettingsTests(unittest.TestCase):
    def setUp(self):
        env = without_smtp()
        self.addCleanup(env.stop)

    def test_missing_credentials_raise_instead_of_defaulting(self):
        self.assertFalse(email_service.smtp_configured())
        with self.assertRaises(email_service.SmtpNotConfigured):
            email_service.smtp_settings()
        os.environ["SMTP_USER"] = "someone@example.com"
        with self.assertRaises(email_service.SmtpNotConfigured):
            email_service.smtp_settings()

    def test_settings_come_from_the_environment(self):
        os.environ.update({"SMTP_USER": "u@example.com", "SMTP_PASSWORD": "pw", "SMTP_PORT": "2525"})
        self.assertEqual(email_service.smtp_settings(), ("smtp.gmail.com", 2525, "u@example.com", "pw"))


if __name__ == "__main__":
    unittest.main()
