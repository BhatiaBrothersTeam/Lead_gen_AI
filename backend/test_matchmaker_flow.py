"""
Lead Matchmaker end to end, inside the real FastAPI app with the real
PostgreSQL database (DATABASE_URL) in a throwaway schema, a stand-in Staff
Portal for sign-in/permissions, and no outside network (website fetches,
search and AI are stubbed).

Website enquiry -> saved + confirmed -> background analysis -> requested vs
suggested products -> WhatsApp/email drafts -> send; plus outbound prospects
(manual + upload), duplicates, missing information and failed analyses.

    .\\venv\\Scripts\\python.exe -m unittest backend.test_matchmaker_flow -v

Skipped when the database is unreachable.
"""
import asyncio
import io
import json
import os
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import asyncpg
import jwt
from openpyxl import Workbook

from backend.api.routes import access
from backend.main import app  # loads .env / .env.local first

TEST_SCHEMA = "matchmaker_test"
API_KEY = "bbp_test-key"
SESSION_SECRET = "test-session-secret"
WEBSITE_KEY = "test-website-key-0123456789-abcdefghijklmnop"

LEAD_USER = ["leads.export", "leads.generate", "leads.save", "outreach.send_email"]
OUTREACH_ADMIN = LEAD_USER + ["outreach.send_bulk", "outreach.manage_templates", "outreach.test_smtp"]
PORTAL = {
    "sales": {"allowed": True, "permissions": LEAD_USER},
    "admin": {"allowed": True, "permissions": OUTREACH_ADMIN},
    "viewer": {"allowed": True, "permissions": ["leads.save"]},
    "outsider": {"allowed": False, "reason": "access_disabled"},
}
ACTIVITY: list = []

SITE_TEXT = {
    "acmeauto.example": "Acme Auto Services is a multi-brand car repair workshop in Dubai with 12 service bays, "
                        "brake and tyre service, fleet maintenance for logistics companies and a parts warehouse.",
}


class FakePortal(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        username = parse_qs(url.query).get("username", [""])[0]
        answer = PORTAL.get(username, {"allowed": False, "reason": "unknown_user"})
        self._send(200, {"roles": [], "permissions": [], "maxAgeSeconds": 60, "reason": None, **answer})

    def do_POST(self):
        ACTIVITY.append(json.loads(self.rfile.read(int(self.headers.get("content-length", 0)))))
        self._send(201, {"id": "x"})


def fake_fetch(url, timeout=8.0, transport=None):
    for host, text in SITE_TEXT.items():
        if host in url:
            return text, ["/about-us"]
    return "", []


def catalogue_workbook() -> bytes:
    wb = Workbook()
    wb.active.title = "Instructions"
    d = wb.create_sheet("Divisions")
    d.append(["Division_Name", "Division_Description", "Target_Countries", "Active"])
    for name in ("Batteries", "Lighting", "Automotive & Car Care"):
        d.append([name, f"{name} range", "United Arab Emirates", "Yes"])
    p = wb.create_sheet("Products_Services")
    p.append(["Division_Name", "Product_Service_Name", "Description", "Applications", "Target_Industries", "Service_Area", "Active"])
    p.append(["Batteries", "AA Batteries", "Alkaline batteries from GP Batteries. Examples: GP Super AA.", "Remote controls, Toys", "Retail, Supermarkets", "United Arab Emirates", "Yes"])
    p.append(["Batteries", "AAA Batteries", "Alkaline AAA from GP Batteries. Examples: GP Super AAA.", "Remote controls", "Retail", "United Arab Emirates", "Yes"])
    p.append(["Lighting", "LED High Bay Lighting", "High bay luminaires from OSRAM. Examples: OSRAM HighBay.", "Warehouse lighting, Workshop lighting", "Warehouses, Logistics, Automotive workshops", "United Arab Emirates", "Yes"])
    p.append(["Automotive & Car Care", "Brake Cleaners", "Brake cleaner from Stegron. Examples: Stegron Brake Clean.", "Brake cleaning, Workshop maintenance", "Automotive workshops, Garages, Fleet operators", "United Arab Emirates", "Yes"])
    p.append(["Automotive & Car Care", "Retired Line", "", "Brake cleaning", "Automotive workshops", "", "No"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def website_payload(**overrides):
    body = {
        "company_name": "Acme Auto Services",
        "contact_person": "Ravi Kumar",
        "business_email": "ravi@acmeauto.example",
        "phone_number": "050 123 4567",
        "country": "United Arab Emirates",
        "city": "Dubai",
        "interested_division": "Batteries",
        "product_service": "AA Batteries",
        "quantity": "200 pcs",
        "requirement_description": "Product: GP Super AA (SKU GP15A)\nMessage: Need for our workshop remotes",
        "additional_notes": "Website reference VVS-TEST-1 (request-price, business customer, en)",
        "source": "vvsgrocer_request_price",
        "whatsapp_same_as_phone": True,
        "form_version": "vvsons-web-1",
        "external_reference": "VVS-TEST-1",
    }
    body.update(overrides)
    return body


async def _drop_schema():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        await conn.execute(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE")
    finally:
        await conn.close()


def _db_reachable() -> bool:
    async def ping():
        conn = await asyncpg.connect(os.environ.get("DATABASE_URL", ""), timeout=5)
        await conn.close()

    try:
        asyncio.run(ping())
        return True
    except Exception:
        return False


@unittest.skipUnless(_db_reachable(), "PostgreSQL (DATABASE_URL) is not reachable")
class MatchmakerFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        cls.portal = ThreadingHTTPServer(("127.0.0.1", 0), FakePortal)
        threading.Thread(target=cls.portal.serve_forever, daemon=True).start()
        cls.env = patch.dict(os.environ, {
            "MATCHMAKER_DB_SCHEMA": TEST_SCHEMA,
            "STAFF_PORTAL_URL": f"http://127.0.0.1:{cls.portal.server_port}",
            "ACTIVITY_LOG_API_KEY": API_KEY,
            "SESSION_SECRET": SESSION_SECRET,
            "MATCHMAKER_ENQUIRY_SECRET": WEBSITE_KEY,
            "SERPER_API_KEY": "",
            "SMTP_USER": "",
            "SMTP_PASSWORD": "",
        })
        cls.env.start()
        asyncio.run(_drop_schema())
        cls.patches = [
            patch("backend.matchmaker.research.fetch_page", side_effect=fake_fetch),
            patch("backend.services.ai_client.ai_configured", return_value=False),
        ]
        for p in cls.patches:
            p.start()
        cls.client = TestClient(app)
        cls.client.__enter__()  # runs startup: DB pool + tables

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        for p in cls.patches:
            p.stop()
        asyncio.run(_drop_schema())
        cls.env.stop()
        cls.portal.shutdown()

    def setUp(self):
        access._cache.clear()
        self.client.cookies.clear()

    # helpers ---------------------------------------------------------------

    def as_user(self, username):
        claims = {"sub": username, "name": "Sara Khan" if username != "admin" else "Admin", "role": "staff",
                  "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
        self.client.cookies.set("lga_session", jwt.encode(claims, SESSION_SECRET, algorithm="HS256"))

    def website(self, body, key=WEBSITE_KEY):
        headers = {"X-LeadMatch-Key": key, "X-LeadMatch-Client-IP": "203.0.113.7"} if key else {}
        return self.client.post("/api/public/enquiry", json=body, headers=headers)

    def wait_analysed(self, lead_id, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            detail = self.client.get(f"/api/matchmaker/leads/{lead_id}").json()
            if detail["lead"]["status"] in ("analysed", "failed") and not detail["queued"]:
                return detail
            time.sleep(0.2)
        self.fail(f"{lead_id} was not analysed in {timeout}s")

    def ensure_catalogue(self):
        self.as_user("admin")
        res = self.client.post(
            "/api/matchmaker/catalogue/import",
            files={"file": ("catalogue.xlsx", catalogue_workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()

    # tests -------------------------------------------------------------------

    def test_01_access_uses_lead_gen_sign_in_and_permissions(self):
        self.assertEqual(self.client.get("/api/matchmaker/summary").status_code, 401)
        self.as_user("outsider")
        self.assertEqual(self.client.get("/api/matchmaker/summary").status_code, 403)
        self.as_user("viewer")  # leads.save only: may look, not add or draft
        self.assertEqual(self.client.get("/api/matchmaker/summary").status_code, 200)
        self.assertEqual(self.client.post("/api/matchmaker/outbound", json={"company_name": "X"}).status_code, 403)
        self.assertEqual(self.client.post("/api/matchmaker/leads/LED-X/drafts", json={}).status_code, 403)
        self.as_user("sales")  # lead user: no catalogue import
        res = self.client.post("/api/matchmaker/catalogue/import", files={"file": ("c.xlsx", b"x", "application/octet-stream")})
        self.assertEqual(res.status_code, 403)

    def test_02_catalogue_import_upserts(self):
        first = self.ensure_catalogue()
        second = self.ensure_catalogue()
        self.assertEqual(second["products"]["inserted"], 0)
        self.assertEqual(second["products"]["updated"], 0)
        self.assertGreaterEqual(first["products"]["inserted"] + first["products"]["skipped"], 5)
        self.as_user("sales")
        names = [p["name"] for p in self.client.get("/api/matchmaker/catalogue").json()["items"]]
        self.assertIn("Brake Cleaners", names)
        self.assertNotIn("Retired Line", names)

    def test_03_website_endpoint_requires_the_shared_key(self):
        self.assertEqual(self.website(website_payload(), key=None).status_code, 401)
        self.assertEqual(self.website(website_payload(), key="wrong").status_code, 401)
        with patch.dict(os.environ, {"MATCHMAKER_ENQUIRY_SECRET": "", "PUBLIC_ENQUIRY_SECRET": ""}):
            self.assertEqual(self.website(website_payload()).status_code, 503)

    def test_04_website_enquiry_end_to_end(self):
        self.ensure_catalogue()
        res = self.website(website_payload())
        self.assertEqual(res.status_code, 201, res.text)
        body = res.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["lead_id"].startswith("LED-"))
        self.assertEqual(body["message"], "Enquiry received")

        # Resending the same website enquiry (e.g. after a timeout) returns the same lead.
        again = self.website(website_payload())
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["lead_id"], body["lead_id"])
        self.assertTrue(again.json()["duplicate"])

        self.as_user("sales")
        detail = self.wait_analysed(body["lead_id"])
        self.assertEqual(detail["lead"]["status"], "analysed", detail["lead"]["error_message"])
        self.assertEqual(detail["company"]["website_domain"], "acmeauto.example")  # from the business email
        self.assertTrue(detail["research"]["website_read"])
        self.assertEqual(detail["requested_items"], ["GP Super AA"])
        self.assertEqual([r["product_name"] for r in detail["requested"]], ["AA Batteries"])
        suggested = [r["product_name"] for r in detail["suggestions"]]
        self.assertIn("Brake Cleaners", suggested)  # workshop -> brake cleaner
        self.assertNotIn("AA Batteries", suggested)
        self.assertNotIn("Retired Line", suggested)
        self.assertEqual(detail["warnings"], [])

        listed = self.client.get("/api/matchmaker/leads", params={"type": "inbound", "q": "VVS-TEST-1"}).json()
        self.assertEqual(listed["total"], 1)
        self.assertEqual(listed["items"][0]["primary_count"], 1)

        # Drafts: requested product + a chosen suggestion, for WhatsApp and email.
        brake = next(r for r in detail["suggestions"] if r["product_name"] == "Brake Cleaners")
        drafts = self.client.post(f"/api/matchmaker/leads/{body['lead_id']}/drafts", json={"recommendation_ids": [brake["id"]]}).json()
        self.assertEqual(drafts["situation"], "requested")
        self.assertTrue(drafts["whatsapp"]["available"])
        self.assertEqual(drafts["whatsapp"]["number"], "971501234567")
        self.assertTrue(drafts["whatsapp"]["url"].startswith("https://wa.me/971501234567?text="))
        self.assertIn("VVS-TEST-1", drafts["whatsapp"]["message"])
        self.assertIn("Brake Cleaners", drafts["email"]["body"])
        self.assertEqual(drafts["email"]["recipient"], "ravi@acmeauto.example")
        self.assertIn("Sara Khan", drafts["email"]["body"])  # signed by the signed-in person
        self.assertFalse(drafts["personalized"])

        # Asking for AI personalisation without a provider falls back with a note.
        ai = self.client.post(f"/api/matchmaker/leads/{body['lead_id']}/drafts", json={"personalize": True}).json()
        self.assertFalse(ai["personalized"])
        self.assertIn("unavailable", ai["ai_error"])

        # A suggestion from another lead cannot be smuggled in.
        bad = self.client.post(f"/api/matchmaker/leads/{body['lead_id']}/drafts", json={"recommendation_ids": ["REC-NOPE"]})
        self.assertEqual(bad.status_code, 400)

        # Sending: refused clearly without SMTP, then sent and logged with SMTP.
        mail = {"recipient": "ravi@acmeauto.example", "subject": drafts["email"]["subject"], "body": drafts["email"]["body"]}
        self.assertEqual(self.client.post(f"/api/matchmaker/leads/{body['lead_id']}/send-email", json=mail).status_code, 503)
        with patch.dict(os.environ, {"SMTP_USER": "u", "SMTP_PASSWORD": "p"}), \
                patch("backend.matchmaker.routes.send_email", AsyncMock(return_value={"success": True})) as sent:
            ok = self.client.post(f"/api/matchmaker/leads/{body['lead_id']}/send-email", json=mail)
        self.assertEqual(ok.json(), {"success": True})
        sent.assert_awaited_once()
        after = self.client.get(f"/api/matchmaker/leads/{body['lead_id']}").json()
        self.assertEqual(after["lead"]["follow_up_status"], "contacted")
        self.assertEqual(after["outreach"][0]["channel"], "email")

        # Feedback and follow-up status.
        fb = self.client.post(f"/api/matchmaker/recommendations/{brake['id']}/feedback", json={"verdict": "relevant"})
        self.assertEqual(fb.json()["feedback"], "relevant")
        self.assertEqual(self.client.patch(f"/api/matchmaker/leads/{body['lead_id']}/follow-up", json={"follow_up_status": "quoted"}).status_code, 200)
        self.assertEqual(self.client.patch(f"/api/matchmaker/leads/{body['lead_id']}/follow-up", json={"follow_up_status": "bogus"}).status_code, 400)

        # Re-analysis keeps sales' verdicts.
        self.client.post(f"/api/matchmaker/leads/{body['lead_id']}/reanalyse")
        again_detail = self.wait_analysed(body["lead_id"])
        brake_again = next(r for r in again_detail["suggestions"] if r["product_name"] == "Brake Cleaners")
        self.assertEqual(brake_again["feedback"], "relevant")

        self.assertTrue(any(a["action"] == "matchmaker.enquiry_received" and a["userId"] == "website" for a in ACTIVITY))
        self.assertTrue(any(a["action"] == "matchmaker.email_sent" and a["userId"] == "sales" for a in ACTIVITY))

    def test_05_missing_information_is_handled(self):
        self.ensure_catalogue()
        no_contact = self.website(website_payload(business_email="", phone_number="", external_reference="VVS-TEST-2"))
        self.assertEqual(no_contact.status_code, 422)
        self.assertIn("email address or phone number", no_contact.json()["detail"])
        bad_email = self.website(website_payload(business_email="not-an-email", external_reference="VVS-TEST-3"))
        self.assertEqual(bad_email.status_code, 422)

        # Phone only, no company, no product, gmail: saved and flagged, not rejected.
        res = self.website({"contact_person": "Mona", "phone_number": "0501112222", "business_email": "mona123@gmail.com",
                            "country": "", "external_reference": "VVS-TEST-4"})
        self.assertEqual(res.status_code, 201, res.text)
        self.as_user("sales")
        detail = self.wait_analysed(res.json()["lead_id"])
        self.assertEqual(detail["lead"]["status"], "analysed")
        self.assertEqual(detail["company"]["name"], "Mona (individual)")
        self.assertEqual(detail["company"]["country"], "United Arab Emirates")
        self.assertIsNone(detail["company"]["website_domain"])  # never gmail.com
        warnings = " ".join(detail["warnings"])
        self.assertIn("names no product", warnings)
        self.assertIn("individual", warnings)
        self.assertEqual(detail["requested"], [])

    def test_06_manual_inbound_confirmation_and_duplicates(self):
        self.ensure_catalogue()
        self.as_user("sales")
        body = {"company_name": "Blue Fleet Logistics", "contact_person": "Omar", "business_email": "omar@bluefleet.example",
                "phone_number": "+971 4 555 0000", "interested_division": "Lighting", "requirement_description": "Warehouse lights"}
        first = self.client.post("/api/matchmaker/inbound", json=body)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertFalse(first.json()["duplicate"])
        self.assertIn("Enquiry saved", first.json()["message"])
        second = self.client.post("/api/matchmaker/inbound", json=body)
        self.assertTrue(second.json()["duplicate"])
        self.assertEqual(second.json()["lead_id"], first.json()["lead_id"])
        detail = self.wait_analysed(first.json()["lead_id"])
        self.assertEqual([r["product_name"] for r in detail["requested"]], ["LED High Bay Lighting"])
        self.assertEqual(detail["lead"]["created_by"], "sales")

    def test_07_outbound_manual_and_upload(self):
        self.ensure_catalogue()
        self.as_user("sales")
        res = self.client.post("/api/matchmaker/outbound", json={
            "company_name": "Gulf Garage LLC", "industry": "Automotive workshops", "city": "Sharjah",
            "description": "Car repair garage and fleet maintenance", "contact_person": "Ali", "phone": "0559998888",
        })
        self.assertEqual(res.status_code, 200, res.text)
        lead_id = res.json()["lead_id"]
        dup = self.client.post("/api/matchmaker/outbound", json={"company_name": "Gulf Garage L.L.C.", "city": "Sharjah"})
        self.assertTrue(dup.json()["duplicate"])
        self.assertEqual(dup.json()["lead_id"], lead_id)
        detail = self.wait_analysed(lead_id)
        self.assertEqual(detail["requested"], [])
        self.assertTrue(detail["suggestions"])
        self.assertTrue(all(r["recommendation_type"] == "potential_opportunity" for r in detail["suggestions"]))
        self.assertIn("Brake Cleaners", [r["product_name"] for r in detail["suggestions"]])
        intro = self.client.post(f"/api/matchmaker/leads/{lead_id}/drafts", json={}).json()
        self.assertEqual(intro["situation"], "introduction")
        self.assertTrue(intro["whatsapp"]["available"])
        self.assertFalse(intro["email"]["available"])  # no email on file: not invented
        self.assertIn("No email", intro["email"]["reason"])

        csv_file = (
            "Company_Name,Country,Website,Industry,Business_Email\n"
            "Desert Logistics,United Arab Emirates,https://desertlog.example,Logistics,\n"
            "Desert Logistics,United Arab Emirates,https://desertlog.example,Logistics,\n"
            ",United Arab Emirates,,,\n"
            "Gulf Garage LLC,United Arab Emirates,,Automotive workshops,\n"
            "Bad Mail Co,India,,,nope\n"
        ).encode()
        preview = self.client.post("/api/matchmaker/outbound/preview", files={"file": ("prospects.csv", csv_file, "text/csv")})
        self.assertEqual(preview.status_code, 200, preview.text)
        p = preview.json()
        self.assertEqual((p["new"], p["duplicate"], p["invalid"]), (1, 1, 2))
        self.assertEqual(p["existing"], 1)  # Gulf Garage is already a prospect
        confirm = self.client.post(f"/api/matchmaker/outbound/batches/{p['batch_id']}/confirm").json()
        self.assertEqual((confirm["created"], confirm["merged"], confirm["failed"]), (1, 1, 0))
        self.assertEqual(self.client.post(f"/api/matchmaker/outbound/batches/{p['batch_id']}/confirm").status_code, 409)
        listed = self.client.get("/api/matchmaker/leads", params={"type": "outbound", "q": "Desert"}).json()
        self.assertEqual(listed["total"], 1)
        self.wait_analysed(listed["items"][0]["id"])

        bad = self.client.post("/api/matchmaker/outbound/preview", files={"file": ("x.xlsx", b"not a workbook", "application/octet-stream")})
        self.assertEqual(bad.status_code, 400)

    def test_08_failed_analysis_is_recorded_and_can_be_retried(self):
        self.ensure_catalogue()
        self.as_user("sales")
        with patch("backend.matchmaker.jobs.research", AsyncMock(side_effect=RuntimeError("boom"))):
            res = self.client.post("/api/matchmaker/outbound", json={"company_name": "Fragile Trading", "website": "fragile.example"})
            failed = self.wait_analysed(res.json()["lead_id"])
        self.assertEqual(failed["lead"]["status"], "failed")
        self.assertIn("boom", failed["lead"]["error_message"])
        retry = self.client.post(f"/api/matchmaker/leads/{res.json()['lead_id']}/reanalyse")
        self.assertEqual(retry.status_code, 200)
        ok = self.wait_analysed(res.json()["lead_id"])
        self.assertEqual(ok["lead"]["status"], "analysed")
        self.assertIsNone(ok["lead"]["error_message"])

    def test_10_a_website_found_by_search_is_flagged_for_checking(self):
        self.ensure_catalogue()
        self.as_user("sales")
        found = AsyncMock(return_value=("https://acmeauto.example", []))
        with patch("backend.matchmaker.research.find_website", found):
            res = self.client.post("/api/matchmaker/outbound", json={"company_name": "Acme Auto Workshop Group"})
            detail = self.wait_analysed(res.json()["lead_id"])
        found.assert_awaited_once()
        self.assertEqual(detail["company"]["website"], "https://acmeauto.example")
        self.assertTrue(detail["research"]["website_read"])
        self.assertTrue(any("found by a web search" in w for w in detail["warnings"]), detail["warnings"])
        # Still flagged after a re-analysis that reuses the saved website.
        self.client.post(f"/api/matchmaker/leads/{res.json()['lead_id']}/reanalyse")
        again = self.wait_analysed(res.json()["lead_id"])
        self.assertTrue(any("found by a web search" in w for w in again["warnings"]))

    def test_09_export_csv(self):
        self.ensure_catalogue()
        self.as_user("viewer")
        self.assertEqual(self.client.get("/api/matchmaker/export/leads.csv").status_code, 403)
        self.as_user("sales")
        res = self.client.get("/api/matchmaker/export/leads.csv")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Lead ID,Type,Status", res.text.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
