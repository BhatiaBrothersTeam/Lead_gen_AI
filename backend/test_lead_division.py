import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.api.routes import leads as routes
from backend.models.lead_models import GenerateLeadsInput, Lead
from backend.services import database


class LeadDivisionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.conn.execute = AsyncMock()
        self.conn.fetch = AsyncMock(return_value=[])
        self.conn.fetchval = AsyncMock(return_value=1)
        self.conn.fetchrow = AsyncMock()
        self.pool = MagicMock()
        self.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=self.conn)
        self.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        self.pool_patch = patch.object(database, "get_pool", AsyncMock(return_value=self.pool))
        self.pool_patch.start()
        self.addCleanup(self.pool_patch.stop)

    def test_model_preserves_division(self):
        self.assertEqual(Lead(division="ISD").model_dump()["division"], "ISD")
        self.assertEqual(Lead().division, "Not Specified")

    async def test_initialize_adds_division_to_existing_table(self):
        await database.initialize_tables()
        statements = [call.args[0] for call in self.conn.execute.call_args_list]
        self.assertIn(
            "ALTER TABLE public.leads ADD COLUMN division text NOT NULL DEFAULT 'Not Specified'",
            statements,
        )

    async def test_direct_save_normalizes_division(self):
        for raw_division, expected in [(" ISD ", "ISD"), (None, "Not Specified"), ("  ", "Not Specified")]:
            with self.subTest(division=raw_division):
                self.conn.fetchrow.return_value = {"id": 1, "division": expected}
                result = await database.save_leads_directly([{"division": raw_division}])
                query, *params = self.conn.fetchrow.call_args.args
                self.assertIn("division, verified", query)
                self.assertEqual(len(params), 12)
                self.assertEqual(params[-1], expected)
                self.assertEqual(result["leads"][0]["division"], expected)

    async def test_generation_insert_and_match_include_division(self):
        for raw_division, expected in [(" Auto Division ", "Auto Division"), ("", "Not Specified")]:
            with self.subTest(division=raw_division):
                self.conn.fetchrow.reset_mock()
                self.conn.fetchrow.side_effect = [None, {"id": 1, "division": expected}]
                result = await database.save_or_update_leads([
                    {"company": "Example", "email": "sales@example.com", "division": raw_division}
                ])
                lookup, insert = self.conn.fetchrow.call_args_list
                self.assertIn("WHERE (", lookup.args[0])
                self.assertIn("AND LOWER(division) = LOWER($3)", lookup.args[0])
                self.assertEqual(lookup.args[-1], expected)
                self.assertIn("division, verified", insert.args[0])
                self.assertEqual(len(insert.args[1:]), 12)
                self.assertEqual(insert.args[-1], expected)
                self.assertEqual(result["newLeadsAdded"], 1)
                self.assertEqual(result["leads"][0]["division"], expected)

    async def test_same_division_duplicate_keeps_original_record(self):
        self.conn.fetchrow.return_value = {"id": 1, "company": "Example", "division": "ISD"}
        result = await database.save_or_update_leads([{"company": "Example", "division": "isd"}])
        self.assertEqual(result["duplicatesSkipped"], 1)
        self.assertEqual(result["newLeadsAdded"], 0)
        self.assertEqual(result["leads"][0]["division"], "ISD")
        self.conn.fetchrow.assert_awaited_once()

    async def test_existing_lead_filter_is_division_specific(self):
        self.conn.fetch.return_value = [
            {"email": "sales@example.com", "phone": "123", "linkedin": "example", "division": "ISD"}
        ]
        same_division = {"email": "sales@example.com", "division": " isd "}
        other_division = {"email": "sales@example.com", "division": "Auto Division"}
        result = await database.filter_existing_leads([same_division, other_division])
        self.assertEqual(result, [other_division])

    async def test_pipeline_attaches_input_division_before_saving(self):
        for raw_division, expected in [(" ISD ", "ISD"), (None, "Not Specified"), ("  ", "Not Specified")]:
            with self.subTest(division=raw_division):
                generated_lead = {"company": "Example", "division": "AI guess"}
                save = AsyncMock(return_value={"leads": [{"company": "Example", "division": expected}]})
                with (
                    patch.object(routes, "analyze_product", AsyncMock(return_value={"searchKeywords": ["supplier"]})),
                    patch.object(routes, "discover_companies", AsyncMock(return_value=[{"url": "example.com"}])),
                    patch.object(routes, "extract_leads", AsyncMock(return_value=[generated_lead])),
                    patch.object(routes, "enrich_leads", AsyncMock(return_value=[generated_lead])),
                    patch.object(routes, "validate_leads", return_value=[generated_lead]),
                    patch.object(database, "save_or_update_leads", save),
                    patch.object(routes, "_log_activity"),  # the Staff Portal activity log isn't under test here
                ):
                    response = await routes.generate_leads(GenerateLeadsInput(productName="Pump", division=raw_division), MagicMock())
                    events = [json.loads(chunk.removeprefix("data: ")) async for chunk in response.body_iterator]
                save.assert_awaited_once_with([{"company": "Example", "division": expected}])
                self.assertEqual(events[-1]["status"], "completed")
                self.assertEqual(events[-1]["leads"][0]["division"], expected)


if __name__ == "__main__":
    unittest.main()