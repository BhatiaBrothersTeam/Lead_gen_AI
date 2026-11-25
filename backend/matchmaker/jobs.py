"""
Background analysis: research the company, match the catalogue, store the
suggestions. Runs as asyncio tasks inside the API process, at most
MATCHMAKER_CONCURRENCY at a time (default 3), so saving an enquiry returns at
once and the analysis follows.

A lead's status tells sales where it is:
  pending -> researching -> analysed | failed (error_message says why; Retry re-runs it)

Leads left pending/researching by a restart are picked up again at startup
(resume_unfinished), at most 3 attempts each.
"""
from __future__ import annotations

import asyncio
import logging
import os

from backend.database.connection import get_pool

from . import repository as repo
from .matching import match_products
from .research import MODEL_VERSION, research

logger = logging.getLogger(__name__)

_semaphore: asyncio.Semaphore | None = None
_tasks: set[asyncio.Task] = set()
_queued: set[str] = set()


def _sem() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(max(1, int(os.getenv("MATCHMAKER_CONCURRENCY", "3") or 3)))
    return _semaphore


def enqueue(lead_id: str, force_research: bool = False) -> bool:
    """Start analysing `lead_id` in the background. False if it is already queued."""
    if lead_id in _queued:
        return False
    _queued.add(lead_id)
    task = asyncio.get_running_loop().create_task(_run(lead_id, force_research))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return True


def is_queued(lead_id: str) -> bool:
    return lead_id in _queued


async def wait_idle(timeout: float = 120.0) -> None:
    """Wait for all queued analyses (tests and shutdown)."""
    if _tasks:
        await asyncio.wait(list(_tasks), timeout=timeout)


async def _run(lead_id: str, force_research: bool) -> None:
    try:
        async with _sem():
            await analyse_lead(lead_id, force_research)
    except Exception:  # noqa: BLE001 -- analyse_lead records the failure on the lead
        logger.exception("Lead Matchmaker analysis of %s failed", lead_id)
    finally:
        _queued.discard(lead_id)


def _enquiry_facts(lead) -> dict | None:
    if lead.lead_type != "inbound":
        return {"notes": lead.additional_notes} if lead.additional_notes else None
    keys = ("interested_division", "interested_product", "quantity", "application", "requirement_description", "technical_requirements")
    facts = {k: lead.get(k) for k in keys if lead.get(k)}
    return facts or None


async def analyse_lead(lead_id: str, force_research: bool = False) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        lead = await repo.get_lead(conn, lead_id)
        if not lead:
            return {"lead_id": lead_id, "status": "missing"}
        await repo.set_lead_status(conn, lead_id, "researching")
        company = await repo.get_company(conn, lead.company_id)

    try:
        # Reuse a recent analysis of the same company (another enquiry, a
        # re-upload) unless sales asked for a fresh one.
        async with pool.acquire() as conn:
            existing = await repo.latest_research(conn, company.id)
        fresh_enough = existing and not force_research and existing.researched_at and (
            (await _age_hours(existing.researched_at)) < 72
        )
        if fresh_enough:
            profile_row = existing
        else:
            # Individuals ("Jane (individual)") have no company site to look up.
            searchable = "(individual)" not in (company.name or "")
            profile = await research(company, _enquiry_facts(lead), allow_search=searchable)
            async with pool.acquire() as conn:
                profile_row = await repo.save_research(conn, company, lead_id, profile)

        async with pool.acquire() as conn:
            products = await repo.active_products(conn)
            matches = match_products(company, profile_row, lead, products)
            async with conn.transaction():
                await repo.replace_recommendations(conn, company.id, lead_id, matches, MODEL_VERSION)
                note = None if products else "The product catalogue is empty: import it under Lead Matchmaker -> Catalogue."
                await repo.set_lead_status(conn, lead_id, "analysed", note, analysed=True)
        return {"lead_id": lead_id, "status": "analysed", "recommendations": len(matches)}
    except Exception as exc:
        async with pool.acquire() as conn:
            await repo.set_lead_status(conn, lead_id, "failed", f"Analysis failed: {type(exc).__name__}: {exc}"[:500])
        raise


async def _age_hours(when) -> float:
    from datetime import datetime, timezone

    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).total_seconds() / 3600


async def resume_unfinished() -> int:
    """Queue leads whose analysis was interrupted (called at startup)."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            ids = await repo.leads_to_resume(conn)
    except Exception as exc:  # noqa: BLE001 -- never block startup
        logger.error("Could not look for unfinished Lead Matchmaker analyses: %s", type(exc).__name__)
        return 0
    for lead_id in ids:
        enqueue(lead_id)
    if ids:
        logger.info("Resumed %d unfinished Lead Matchmaker analyses", len(ids))
    return len(ids)
