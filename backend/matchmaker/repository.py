"""
Database access for the Lead Matchmaker module (asyncpg, Lead Gen's pool).

Company identity (find / upsert) is ported from LeadMatch: one company per
business, recognised by website / business-email domain (when the names agree),
then name + city + country, then name + country.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import Row, loads, new_id, row, rows, t
from .utils import digits_only, email_domain, names_compatible, normalize_company, normalize_domain

COMPANY_FIELDS = (
    "website", "industry", "sub_industry", "description", "city", "state", "country", "business_type", "notes", "source",
)
# Fields a later enquiry or upload may fill in, but never overwrite.
KEEP_FIRST = {"notes", "description", "source"}

LEAD_FIELDS = (
    "lead_type", "status", "source", "campaign", "interested_division", "interested_product", "quantity",
    "application", "technical_requirements", "timeline", "requirement_description", "additional_notes",
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "landing_page", "referrer",
    "form_version", "external_reference", "submitted_company_name", "contact_person", "contact_email",
    "contact_phone", "batch_id", "created_by",
)


# --- companies & contacts ---------------------------------------------------

async def find_company(conn, name=None, website=None, email=None, city=None, country=None) -> tuple[Row | None, str]:
    domain = normalize_domain(website) or email_domain(email)
    if domain:
        for match in rows(await conn.fetch(f"SELECT * FROM {t('companies')} WHERE website_domain = $1 ORDER BY created_at", domain)):
            if names_compatible(name, match.name):
                return match, "domain"
    nname = normalize_company(name)
    if nname and city and country:
        match = row(await conn.fetchrow(
            f"SELECT * FROM {t('companies')} WHERE name_normalized = $1 AND lower(city) = lower($2) AND lower(country) = lower($3) LIMIT 1",
            nname, city.strip(), country.strip(),
        ))
        if match:
            return match, "name_city_country"
    if nname and country:
        match = row(await conn.fetchrow(
            f"SELECT * FROM {t('companies')} WHERE name_normalized = $1 AND lower(country) = lower($2) LIMIT 1",
            nname, country.strip(),
        ))
        if match:
            return match, "name_country"
    return None, "new"


async def upsert_company(conn, payload: dict) -> tuple[Row, str]:
    existing, how = await find_company(
        conn, payload.get("name"), payload.get("website"), payload.get("email"), payload.get("city"), payload.get("country")
    )
    domain = normalize_domain(payload.get("website")) or email_domain(payload.get("email"))
    if existing:
        updates = {
            f: payload[f] for f in COMPANY_FIELDS
            if payload.get(f) and not existing.get(f)
        }
        if domain and not existing.website_domain:
            updates["website_domain"] = domain
        if updates:
            sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(updates))
            existing = row(await conn.fetchrow(
                f"UPDATE {t('companies')} SET {sets}, updated_at = now() WHERE id = $1 RETURNING *",
                existing.id, *updates.values(),
            ))
        return existing, how
    company = row(await conn.fetchrow(
        f"""INSERT INTO {t('companies')} (id, name, name_normalized, website, website_domain, country, city, state,
                industry, sub_industry, business_type, description, source, notes)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14) RETURNING *""",
        new_id("COM"), payload["name"].strip(), normalize_company(payload["name"]), payload.get("website"), domain,
        payload.get("country"), payload.get("city"), payload.get("state"), payload.get("industry"),
        payload.get("sub_industry"), payload.get("business_type"), payload.get("description"),
        payload.get("source"), payload.get("notes"),
    ))
    return company, "new"


async def upsert_contact(conn, company_id: str, person=None, email=None, phone=None, whatsapp=None, designation=None, verified=True) -> None:
    """Reuse the company's contact when the same person writes again (same email or phone)."""
    email = (email or "").strip().lower() or None
    phone_digits = digits_only(phone)
    if not (person or email or phone):
        return
    for c in rows(await conn.fetch(f"SELECT * FROM {t('contacts')} WHERE company_id = $1", company_id)):
        same_email = email and (c.email or "").strip().lower() == email
        same_phone = phone_digits and digits_only(c.phone) == phone_digits
        if same_email or same_phone:
            await conn.execute(
                f"""UPDATE {t('contacts')} SET contact_person = COALESCE($2, contact_person),
                        email = COALESCE(email, $3), phone = COALESCE(phone, $4), whatsapp = COALESCE(whatsapp, $5),
                        designation = COALESCE(designation, $6), updated_at = now() WHERE id = $1""",
                c.id, person, email, phone, whatsapp, designation,
            )
            return
    await conn.execute(
        f"""INSERT INTO {t('contacts')} (id, company_id, contact_person, designation, email, phone, whatsapp, is_verified)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
        new_id("CTC"), company_id, person, designation, email, phone, whatsapp, verified,
    )


# --- leads ------------------------------------------------------------------

async def lead_by_reference(conn, reference: str) -> Row | None:
    return row(await conn.fetchrow(f"SELECT * FROM {t('leads')} WHERE external_reference = $1", reference))


async def recent_duplicate_inbound(conn, email: str | None, phone: str | None, product: str | None, requirement: str | None, hours: int = 24) -> Row | None:
    """The same person asking for the same thing again within `hours` (e.g. a double submit)."""
    if not (email or phone):
        return None
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    candidates = rows(await conn.fetch(
        f"""SELECT * FROM {t('leads')} WHERE lead_type = 'inbound' AND created_at >= $1
            AND (($2::text IS NOT NULL AND lower(contact_email) = lower($2)) OR ($3::text IS NOT NULL AND contact_phone IS NOT NULL))
            ORDER BY created_at DESC LIMIT 50""",
        since, email, digits_only(phone) or None,
    ))
    phone_digits = digits_only(phone)
    for lead in candidates:
        same_person = (email and (lead.contact_email or "").lower() == email.lower()) or (
            phone_digits and digits_only(lead.contact_phone) == phone_digits
        )
        same_request = (lead.interested_product or "").strip().lower() == (product or "").strip().lower() and (
            (lead.requirement_description or "").strip() == (requirement or "").strip()
        )
        if same_person and same_request:
            return lead
    return None


async def outbound_lead_for_company(conn, company_id: str) -> Row | None:
    return row(await conn.fetchrow(
        f"SELECT * FROM {t('leads')} WHERE company_id = $1 AND lead_type = 'outbound' ORDER BY created_at DESC LIMIT 1",
        company_id,
    ))


async def create_lead(conn, company_id: str, data: dict) -> Row:
    fields = {k: data.get(k) for k in LEAD_FIELDS if data.get(k) is not None}
    fields.setdefault("status", "pending")
    cols = ["id", "company_id", *fields.keys()]
    params = ", ".join(f"${i + 1}" for i in range(len(cols)))
    return row(await conn.fetchrow(
        f"INSERT INTO {t('leads')} ({', '.join(cols)}) VALUES ({params}) RETURNING *",
        new_id("LED"), company_id, *fields.values(),
    ))


async def set_lead_status(conn, lead_id: str, status: str, error: str | None = None, analysed: bool = False) -> None:
    await conn.execute(
        f"""UPDATE {t('leads')} SET status = $2, error_message = $3, updated_at = now(),
                analysed_at = CASE WHEN $4 THEN now() ELSE analysed_at END,
                attempts = attempts + CASE WHEN $2 = 'researching' THEN 1 ELSE 0 END
            WHERE id = $1""",
        lead_id, status, error, analysed,
    )


async def get_lead(conn, lead_id: str) -> Row | None:
    return row(await conn.fetchrow(f"SELECT * FROM {t('leads')} WHERE id = $1", lead_id))


async def get_company(conn, company_id: str) -> Row | None:
    return row(await conn.fetchrow(f"SELECT * FROM {t('companies')} WHERE id = $1", company_id))


async def contacts_for(conn, company_id: str) -> list[Row]:
    return rows(await conn.fetch(f"SELECT * FROM {t('contacts')} WHERE company_id = $1 ORDER BY created_at", company_id))


async def latest_research(conn, company_id: str) -> Row | None:
    r = row(await conn.fetchrow(
        f"SELECT * FROM {t('research')} WHERE company_id = $1 ORDER BY researched_at DESC LIMIT 1", company_id
    ))
    if r:
        r.sources = loads(r.sources, [])
    return r


async def website_found_by_search(conn, company: Row) -> str | None:
    """The company's website, if it came from a web search rather than from the buyer or sales."""
    if not company.website:
        return None
    found = await conn.fetchval(
        f"SELECT found_website FROM {t('research')} WHERE company_id = $1 AND found_website IS NOT NULL "
        "ORDER BY researched_at DESC LIMIT 1",
        company.id,
    )
    return found if found and normalize_domain(found) == normalize_domain(company.website) else None


async def save_research(conn, company: Row, lead_id: str | None, profile: dict) -> Row:
    r = row(await conn.fetchrow(
        f"""INSERT INTO {t('research')} (id, company_id, lead_id, industry, business_type, products_manufactured,
                services_offered, business_activities, facilities, procurement_areas, relevant_applications, summary,
                sources, website_read, method, model_version, found_website)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb,$14,$15,$16,$17) RETURNING *""",
        new_id("RSH"), company.id, lead_id, profile.get("industry"), profile.get("business_type"),
        profile.get("products_manufactured"), profile.get("services_offered"), profile.get("business_activities"),
        profile.get("facilities"), profile.get("procurement_areas"), profile.get("relevant_applications"),
        profile.get("summary"), json.dumps(profile.get("sources") or []), bool(profile.get("website_read")),
        profile.get("method"), profile.get("model_version"), profile.get("found_website"),
    ))
    r.sources = loads(r.sources, [])
    # Fill gaps on the company from the research, never overwrite what people entered.
    fill = {
        "industry": profile.get("industry") if (profile.get("industry") or "") != "General B2B" else None,
        "business_type": profile.get("business_type"),
        "description": profile.get("summary"),
        "website": profile.get("found_website"),
        "website_domain": normalize_domain(profile.get("found_website")),
    }
    updates = {k: v for k, v in fill.items() if v and not company.get(k)}
    if updates:
        sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(updates))
        await conn.execute(f"UPDATE {t('companies')} SET {sets}, updated_at = now() WHERE id = $1", company.id, *updates.values())
        company.update(updates)
    return r


async def active_products(conn) -> list[Row]:
    return rows(await conn.fetch(
        f"""SELECT p.*, d.name AS division_name, d.is_active AS division_active
            FROM {t('products')} p JOIN {t('divisions')} d ON d.id = p.division_id
            WHERE p.is_active AND d.is_active ORDER BY d.name, p.name"""
    ))


async def replace_recommendations(conn, company_id: str, lead_id: str, items: list[dict], model_version: str) -> None:
    # Keep sales' verdicts on lines that are suggested again.
    feedback = {
        r["product_id"]: (r["feedback"], r["feedback_by"])
        for r in await conn.fetch(
            f"SELECT product_id, feedback, feedback_by FROM {t('recommendations')} WHERE lead_id = $1 AND feedback IS NOT NULL", lead_id
        )
    }
    await conn.execute(f"DELETE FROM {t('recommendations')} WHERE lead_id = $1", lead_id)
    for rank, item in enumerate(items, 1):
        fb, fb_by = feedback.get(item["product"].id, (None, None))
        await conn.execute(
            f"""INSERT INTO {t('recommendations')} (id, company_id, lead_id, product_id, recommendation_type, relevance_score,
                    confidence, reason, activity, evidence_summary, evidence_url, verification_status, sales_verify,
                    model_version, feedback, feedback_by, rank)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)""",
            new_id("REC"), company_id, lead_id, item["product"].id, item["recommendation_type"], item["score"],
            item["confidence"], item["reason"], item["activity"], item["evidence_summary"], item["evidence_url"],
            item["verification_status"], item["sales_verify"], model_version, fb, fb_by, rank,
        )


async def recommendations_for(conn, lead_id: str) -> list[Row]:
    return rows(await conn.fetch(
        f"""SELECT r.*, p.name AS product_name, p.description AS product_description, p.applications AS product_applications,
                   p.product_url, p.sku AS product_sku, d.name AS division
            FROM {t('recommendations')} r
            JOIN {t('products')} p ON p.id = r.product_id
            JOIN {t('divisions')} d ON d.id = p.division_id
            WHERE r.lead_id = $1
            ORDER BY (r.recommendation_type = 'primary_requirement') DESC, r.rank NULLS LAST, r.relevance_score DESC""",
        lead_id,
    ))


async def list_leads(conn, lead_type: str | None, status: str | None, q: str | None, page: int, page_size: int) -> tuple[list[Row], int]:
    where, params = [], []
    if lead_type:
        params.append(lead_type)
        where.append(f"l.lead_type = ${len(params)}")
    if status:
        params.append(status)
        where.append(f"l.status = ${len(params)}")
    if q:
        params.append(f"%{q.strip()}%")
        n = len(params)
        where.append(
            f"(c.name ILIKE ${n} OR l.id ILIKE ${n} OR l.external_reference ILIKE ${n} OR l.submitted_company_name ILIKE ${n} "
            f"OR l.contact_person ILIKE ${n} OR l.contact_email ILIKE ${n} OR l.interested_product ILIKE ${n})"
        )
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    base = f"FROM {t('leads')} l JOIN {t('companies')} c ON c.id = l.company_id {clause}"
    total = await conn.fetchval(f"SELECT count(*) {base}", *params)
    params += [page_size, (page - 1) * page_size]
    items = rows(await conn.fetch(
        f"""SELECT l.*, c.name AS company_name, c.country AS company_country, c.industry AS company_industry,
                   c.website AS company_website,
                   (SELECT count(*) FROM {t('recommendations')} r WHERE r.lead_id = l.id AND r.recommendation_type = 'primary_requirement') AS primary_count,
                   (SELECT count(*) FROM {t('recommendations')} r WHERE r.lead_id = l.id AND r.recommendation_type <> 'primary_requirement') AS suggestion_count
            {base} ORDER BY l.created_at DESC LIMIT ${len(params) - 1} OFFSET ${len(params)}""",
        *params,
    ))
    return items, total


async def stats(conn) -> dict[str, Any]:
    r = await conn.fetchrow(
        f"""SELECT
              count(*) FILTER (WHERE lead_type = 'inbound') AS inbound,
              count(*) FILTER (WHERE lead_type = 'outbound') AS outbound,
              count(*) FILTER (WHERE status IN ('pending', 'researching')) AS in_progress,
              count(*) FILTER (WHERE status = 'failed') AS failed,
              count(*) FILTER (WHERE lead_type = 'inbound' AND created_at >= now() - interval '7 days') AS inbound_7d
            FROM {t('leads')}"""
    )
    products = await conn.fetchval(
        f"SELECT count(*) FROM {t('products')} p JOIN {t('divisions')} d ON d.id = p.division_id WHERE p.is_active AND d.is_active"
    )
    return {**dict(r), "catalogue_products": products}


async def leads_to_resume(conn) -> list[str]:
    """Leads whose analysis never finished (e.g. the server restarted mid-way)."""
    return [r["id"] for r in await conn.fetch(
        f"SELECT id FROM {t('leads')} WHERE status IN ('pending', 'researching') AND attempts < 3 ORDER BY created_at LIMIT 200"
    )]


async def log_outreach(conn, lead_id, company_id, channel, recipient, subject, status, error, user) -> None:
    await conn.execute(
        f"""INSERT INTO {t('outreach_log')} (id, lead_id, company_id, channel, recipient, subject, status, error, created_by)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
        new_id("OUT"), lead_id, company_id, channel, recipient, subject, status, error, user,
    )


async def outreach_history(conn, lead_id: str) -> list[Row]:
    return rows(await conn.fetch(
        f"SELECT * FROM {t('outreach_log')} WHERE lead_id = $1 ORDER BY created_at DESC LIMIT 50", lead_id
    ))
