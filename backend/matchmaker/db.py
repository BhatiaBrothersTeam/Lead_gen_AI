"""
Lead Matchmaker tables, in their own PostgreSQL schema next to Lead Gen's
public.leads (so "leads", "companies" etc. never collide with Lead Gen's own
tables). The schema name comes from MATCHMAKER_DB_SCHEMA (default
"matchmaker"); tests use a throwaway one.

Uses the Lead Gen backend's asyncpg pool (backend.database.connection).
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import date, datetime
from typing import Any, Iterable

from backend.database.connection import get_pool


def schema() -> str:
    name = os.getenv("MATCHMAKER_DB_SCHEMA", "matchmaker").strip() or "matchmaker"
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", name):
        raise RuntimeError("MATCHMAKER_DB_SCHEMA must be a lowercase SQL identifier")
    return name


def t(table: str) -> str:
    """Schema-qualified table name, e.g. t("leads") -> matchmaker.leads."""
    return f"{schema()}.{table}"


def new_id(prefix: str) -> str:
    # Same shape as LeadMatch ("LED-3F9A0C1B2D4E"): the website stores and
    # shows these ids, and links to /leads/<id>.
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


class Row(dict):
    """A database row with attribute access (row.name), None for missing keys.

    The matching and drafting code reads companies, products and leads as
    objects; this keeps it identical to the original LeadMatch logic.
    """

    def __getattr__(self, key: str) -> Any:
        return self.get(key)

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


def row(record) -> Row | None:
    return Row(dict(record)) if record is not None else None


def rows(records: Iterable) -> list[Row]:
    return [Row(dict(r)) for r in records]


def jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    return value


def loads(value: Any, default: Any) -> Any:
    """jsonb columns come back as text from asyncpg unless a codec is set."""
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


async def initialize_matchmaker_tables() -> None:
    s = schema()
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Two app instances starting together must not race on DDL.
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext('lead_matchmaker_schema'))")
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {s}")
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {s}.divisions (
                    id text PRIMARY KEY,
                    name text NOT NULL,
                    name_normalized text NOT NULL UNIQUE,
                    description text,
                    target_countries text,
                    is_active boolean NOT NULL DEFAULT true,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )""")
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {s}.products (
                    id text PRIMARY KEY,
                    division_id text NOT NULL REFERENCES {s}.divisions(id),
                    name text NOT NULL,
                    name_normalized text NOT NULL,
                    sku text,
                    category text,
                    description text,
                    applications text,
                    target_industries text,
                    ideal_buyer_types text,
                    specifications text,
                    complementary_products text,
                    service_area text,
                    exclusions text,
                    product_url text,
                    image_url text,
                    is_active boolean NOT NULL DEFAULT true,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    UNIQUE (division_id, name_normalized)
                )""")
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {s}.companies (
                    id text PRIMARY KEY,
                    name text NOT NULL,
                    name_normalized text NOT NULL,
                    website text,
                    website_domain text,
                    country text,
                    city text,
                    state text,
                    industry text,
                    sub_industry text,
                    business_type text,
                    description text,
                    source text,
                    notes text,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )""")
            await conn.execute(f"CREATE INDEX IF NOT EXISTS ix_mm_company_domain ON {s}.companies (website_domain)")
            await conn.execute(f"CREATE INDEX IF NOT EXISTS ix_mm_company_name ON {s}.companies (name_normalized, country)")
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {s}.contacts (
                    id text PRIMARY KEY,
                    company_id text NOT NULL REFERENCES {s}.companies(id) ON DELETE CASCADE,
                    contact_person text,
                    designation text,
                    email text,
                    phone text,
                    whatsapp text,
                    is_verified boolean NOT NULL DEFAULT false,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )""")
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {s}.batches (
                    id text PRIMARY KEY,
                    filename text NOT NULL,
                    status text NOT NULL DEFAULT 'preview',
                    total_rows int NOT NULL DEFAULT 0,
                    new_count int NOT NULL DEFAULT 0,
                    existing_count int NOT NULL DEFAULT 0,
                    duplicate_count int NOT NULL DEFAULT 0,
                    invalid_count int NOT NULL DEFAULT 0,
                    processed_count int NOT NULL DEFAULT 0,
                    failed_count int NOT NULL DEFAULT 0,
                    preview jsonb,
                    created_by text,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )""")
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {s}.leads (
                    id text PRIMARY KEY,
                    company_id text NOT NULL REFERENCES {s}.companies(id),
                    lead_type text NOT NULL,
                    status text NOT NULL DEFAULT 'pending',
                    follow_up_status text NOT NULL DEFAULT 'new',
                    source text,
                    campaign text,
                    interested_division text,
                    interested_product text,
                    quantity text,
                    application text,
                    technical_requirements text,
                    timeline text,
                    requirement_description text,
                    additional_notes text,
                    utm_source text,
                    utm_medium text,
                    utm_campaign text,
                    utm_content text,
                    utm_term text,
                    landing_page text,
                    referrer text,
                    form_version text,
                    external_reference text,
                    submitted_company_name text,
                    contact_person text,
                    contact_email text,
                    contact_phone text,
                    batch_id text REFERENCES {s}.batches(id),
                    created_by text,
                    error_message text,
                    attempts int NOT NULL DEFAULT 0,
                    analysed_at timestamptz,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )""")
            # One website enquiry = one lead, even if the website resends it.
            await conn.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS ux_mm_lead_external_ref ON {s}.leads (external_reference) "
                "WHERE external_reference IS NOT NULL"
            )
            await conn.execute(f"CREATE INDEX IF NOT EXISTS ix_mm_lead_type ON {s}.leads (lead_type, created_at DESC)")
            await conn.execute(f"CREATE INDEX IF NOT EXISTS ix_mm_lead_status ON {s}.leads (status)")
            await conn.execute(f"CREATE INDEX IF NOT EXISTS ix_mm_lead_company ON {s}.leads (company_id)")
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {s}.research (
                    id text PRIMARY KEY,
                    company_id text NOT NULL REFERENCES {s}.companies(id) ON DELETE CASCADE,
                    lead_id text REFERENCES {s}.leads(id) ON DELETE SET NULL,
                    status text NOT NULL DEFAULT 'completed',
                    industry text,
                    business_type text,
                    products_manufactured text,
                    services_offered text,
                    business_activities text,
                    facilities text,
                    procurement_areas text,
                    relevant_applications text,
                    summary text,
                    sources jsonb,
                    website_read boolean NOT NULL DEFAULT false,
                    method text,
                    model_version text,
                    researched_at timestamptz NOT NULL DEFAULT now()
                )""")
            await conn.execute(f"CREATE INDEX IF NOT EXISTS ix_mm_research_company ON {s}.research (company_id, researched_at DESC)")
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {s}.recommendations (
                    id text PRIMARY KEY,
                    company_id text NOT NULL REFERENCES {s}.companies(id) ON DELETE CASCADE,
                    lead_id text REFERENCES {s}.leads(id) ON DELETE CASCADE,
                    product_id text NOT NULL REFERENCES {s}.products(id),
                    recommendation_type text NOT NULL,
                    relevance_score double precision NOT NULL DEFAULT 0,
                    confidence text NOT NULL DEFAULT 'Low',
                    reason text,
                    activity text,
                    evidence_summary text,
                    evidence_url text,
                    verification_status text,
                    sales_verify text,
                    model_version text,
                    feedback text,
                    feedback_by text,
                    created_at timestamptz NOT NULL DEFAULT now()
                )""")
            # Columns added after the first release (CREATE TABLE IF NOT EXISTS never adds columns).
            await conn.execute(f"ALTER TABLE {s}.recommendations ADD COLUMN IF NOT EXISTS rank int")
            await conn.execute(f"ALTER TABLE {s}.research ADD COLUMN IF NOT EXISTS found_website text")
            await conn.execute(f"CREATE INDEX IF NOT EXISTS ix_mm_rec_lead ON {s}.recommendations (lead_id)")
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {s}.outreach_log (
                    id text PRIMARY KEY,
                    lead_id text REFERENCES {s}.leads(id) ON DELETE CASCADE,
                    company_id text,
                    channel text NOT NULL,
                    recipient text,
                    subject text,
                    status text NOT NULL,
                    error text,
                    created_by text,
                    created_at timestamptz NOT NULL DEFAULT now()
                )""")
