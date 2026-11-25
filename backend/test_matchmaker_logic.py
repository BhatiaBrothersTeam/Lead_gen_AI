"""
Lead Matchmaker logic without a database: product matching, outreach drafts,
phone numbers, Excel parsing and the website-fetch safety check.

    .\\venv\\Scripts\\python.exe -m unittest backend.test_matchmaker_logic -v
"""
import io
import unittest

from openpyxl import Workbook

from backend.matchmaker.db import Row
from backend.matchmaker.excel import parse_outbound_file
from backend.matchmaker.matching import match_products
from backend.matchmaker.outreach import build_draft, international_number, requested_items
from backend.matchmaker.research import heuristic_profile, is_public_url


def product(pid, name, division, industries="", applications="", description="", area="United Arab Emirates", exclusions=None):
    return Row(id=pid, name=name, division_name=division, division_active=True, is_active=True, category=None,
               description=description, applications=applications, target_industries=industries,
               ideal_buyer_types=None, specifications=None, service_area=area, exclusions=exclusions)


CATALOGUE = [
    product("P1", "AA Batteries", "Batteries", "Retail, Supermarkets, Security", "Remote controls, Toys, Alarm sensors",
            "Alkaline batteries from GP Batteries. Examples: GP Super AA."),
    product("P2", "AAA Batteries", "Batteries", "Retail, Supermarkets", "Remote controls, Toys"),
    product("P3", "LED High Bay Lighting", "Lighting", "Warehouses, Logistics, Automotive workshops", "Warehouse lighting, Workshop lighting",
            "High bay luminaires from OSRAM. Examples: OSRAM HighBay."),
    product("P4", "Brake Cleaners", "Automotive & Car Care", "Automotive workshops, Garages, Fleet operators", "Brake cleaning, Workshop maintenance"),
    product("P5", "Industrial Bearings", "Industrial & MRO", "Steel, Cement", "Conveyors", area="India"),
]


def company(**kw):
    base = dict(id="C1", name="Acme Auto Services", industry=None, sub_industry=None, description=None,
                business_type=None, country="United Arab Emirates", website=None, website_domain=None)
    base.update(kw)
    return Row(base)


def research(**kw):
    base = dict(summary=None, business_activities=None, products_manufactured=None, services_offered=None,
                procurement_areas=None, facilities=None, relevant_applications=None, sources=[], website_read=False, industry=None)
    base.update(kw)
    return Row(base)


class MatchingTests(unittest.TestCase):
    def test_inbound_requested_line_is_primary_and_others_are_suggestions(self):
        lead = Row(lead_type="inbound", interested_division="Batteries", interested_product="AA Batteries",
                   requirement_description="Product: GP Super AA (SKU GP15A)", application=None)
        c = company(industry="Automotive workshops")
        r = research(business_activities="car repair, maintenance", facilities="workshop")
        out = match_products(c, r, lead, CATALOGUE)
        primary = [m["product"].name for m in out if m["primary"]]
        others = [m["product"].name for m in out if not m["primary"]]
        self.assertEqual(primary, ["AA Batteries"])  # not AAA: the exact line was named
        self.assertIn("Brake Cleaners", others)
        self.assertIn("LED High Bay Lighting", others)
        self.assertTrue(all(m["recommendation_type"] == "cross_sell" for m in out if not m["primary"]))
        self.assertEqual(out[0]["product"].name, "AA Batteries")

    def test_division_only_enquiry_makes_the_division_the_requirement(self):
        lead = Row(lead_type="inbound", interested_division="Lighting", interested_product=None, requirement_description=None)
        out = match_products(company(), research(), lead, CATALOGUE)
        self.assertEqual([m["product"].name for m in out if m["primary"]], ["LED High Bay Lighting"])

    def test_division_request_narrows_to_the_lines_the_customer_described(self):
        lighting = [
            product("L1", "LED Bulbs", "Lighting", "Facility management", "Office lighting, Corridor lighting"),
            product("L2", "Halogen Lamps", "Lighting", "Facility management", "Display lighting, Spot lighting"),
            product("L3", "Battens & Fixtures", "Lighting", "Facility management", "Car park lighting, Warehouse lighting"),
        ]
        lead = Row(lead_type="inbound", interested_division="Lighting", interested_product=None,
                   requirement_description="Needs LED replacements for car park and corridor lights")
        out = match_products(company(industry="Facility management"), research(), lead, lighting)
        primary = {m["product"].name for m in out if m["primary"]}
        self.assertEqual(primary, {"LED Bulbs", "Battens & Fixtures"})
        halogen = next(m for m in out if m["product"].name == "Halogen Lamps")
        self.assertEqual(halogen["recommendation_type"], "cross_sell")
        # Without describing anything specific, the whole division stays requested.
        vague = Row(lead_type="inbound", interested_division="Lighting", interested_product=None, requirement_description="Please call me")
        out = match_products(company(), research(), vague, lighting)
        self.assertEqual(len([m for m in out if m["primary"]]), 3)

    def test_outbound_gets_potential_opportunities_only_and_respects_service_area(self):
        lead = Row(lead_type="outbound")
        c = company(industry="Steel", description="Steel mill with conveyors")
        out = match_products(c, research(), lead, CATALOGUE)
        names = {m["product"].name: m for m in out}
        self.assertTrue(all(m["recommendation_type"] == "potential_opportunity" and not m["primary"] for m in out))
        # Bearings fit the industry but are only served in India: score heavily reduced.
        if "Industrial Bearings" in names:
            self.assertLess(names["Industrial Bearings"]["score"], 40)

    def test_exclusions_remove_a_line(self):
        p = product("P9", "Toy Batteries", "Batteries", "Retail", "Toys", exclusions="hospital")
        lead = Row(lead_type="outbound")
        out = match_products(company(industry="Retail", description="hospital pharmacy retail"), research(), lead, [p])
        self.assertEqual(out, [])

    def test_inactive_lines_are_never_suggested(self):
        p = product("P8", "Brake Cleaners", "Automotive & Car Care", "Automotive workshops", "Brake cleaning")
        p.is_active = False
        out = match_products(company(industry="Automotive workshops"), research(), Row(lead_type="outbound"), [p])
        self.assertEqual(out, [])


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.c = company(name="Acme Auto Services", industry="Automotive workshops")
        self.inbound = Row(lead_type="inbound", external_reference="VVS-1234", interested_product="AA Batteries",
                           interested_division="Batteries", quantity="200 pcs",
                           requirement_description="Product: GP Super AA (SKU GP15A)\nItems: GP Super AA; GP Super AAA")

    def test_requested_items_come_from_the_enquiry(self):
        self.assertEqual(requested_items(self.inbound), ["GP Super AA", "GP Super AAA"])

    def test_inbound_draft_repeats_the_request_and_offers_chosen_suggestions(self):
        d = build_draft(self.c, self.inbound, [CATALOGUE[0]], [CATALOGUE[3]], "Ravi Kumar", "Sara Khan", None)
        self.assertEqual(d.situation, "requested")
        for text in (d.whatsapp, d.email):
            self.assertIn("VVS-1234", text)
            self.assertIn("GP Super AA", text)
            self.assertIn("Brake Cleaners", text)
            self.assertNotIn("score", text.lower())
        self.assertTrue(d.whatsapp.startswith("Hello Ravi, this is Sara Khan from"))
        self.assertIn("200 pcs", d.email)

    def test_outbound_draft_is_an_introduction_tied_to_the_business(self):
        lead = Row(lead_type="outbound")
        d = build_draft(self.c, lead, [], [CATALOGUE[2], CATALOGUE[3]], None, "", None)
        self.assertEqual(d.situation, "introduction")
        self.assertIn("automotive workshops", d.email.lower())
        self.assertIn("LED High Bay Lighting (OSRAM)", d.email)
        self.assertIn("Dear Acme Auto Services team", d.email)
        self.assertNotIn("enquiry", d.email.lower())  # never claims they asked

    def test_placeholder_contact_names_are_not_used_as_names(self):
        d = build_draft(self.c, self.inbound, [], [], "Website visitor", "", None)
        self.assertTrue(d.whatsapp.startswith("Hello, this is"))


class PhoneAndFileTests(unittest.TestCase):
    def test_international_number(self):
        self.assertEqual(international_number("050 123 4567"), "971501234567")
        self.assertEqual(international_number("+91 98000 00000"), "919800000000")
        self.assertEqual(international_number("00971501234567"), "971501234567")
        self.assertEqual(international_number("501234567"), "971501234567")
        self.assertEqual(international_number(""), "")

    def test_outbound_file_accepts_common_header_names(self):
        wb = Workbook()
        info = wb.active
        info.title = "Instructions"
        info["A1"] = "read me"
        ws = wb.create_sheet("Sheet2")
        ws.append(["Company", "Email", "Phone", "Country"])
        ws.append(["Gulf Garage LLC", "ops@gulfgarage.example", "+971 50 123 4567", "UAE"])
        buf = io.BytesIO()
        wb.save(buf)
        rows = parse_outbound_file(buf.getvalue(), "list.xlsx")
        self.assertEqual(rows[0]["Company_Name"], "Gulf Garage LLC")
        self.assertEqual(rows[0]["Business_Email"], "ops@gulfgarage.example")
        self.assertEqual(rows[0]["Country"], "UAE")

    def test_csv_upload(self):
        rows = parse_outbound_file(b"Company_Name,Country\nAcme,India\n", "x.csv")
        self.assertEqual(rows, [{"Company_Name": "Acme", "Country": "India"}])


class ResearchSafetyTests(unittest.TestCase):
    def test_internal_addresses_are_never_fetched(self):
        for url in ("http://localhost/", "http://127.0.0.1/admin", "http://169.254.169.254/latest", "http://10.0.0.5/",
                    "file:///etc/passwd", "http://example.com:8080/"):
            self.assertFalse(is_public_url(url), url)

    def test_heuristic_profile_without_website(self):
        p = heuristic_profile(company(name="Gulf Garage", description="Car repair workshop and fleet maintenance"), "")
        self.assertEqual(p["industry"], "Automotive")
        self.assertIn("workshop", p["facilities"])


if __name__ == "__main__":
    unittest.main()
