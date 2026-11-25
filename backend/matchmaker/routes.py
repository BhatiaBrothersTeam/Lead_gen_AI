"""
Lead Matchmaker API.

Team routes (/api/matchmaker/*) use the Lead Gen Agent's own Staff Portal
sign-in and permissions; there is no separate Matchmaker login:

  view leads, analyses, catalogue     leads.generate or leads.save
  add prospects, upload, re-analyse   leads.generate
  feedback, follow-up status          leads.save
  CSV export                          leads.export
  WhatsApp / email drafts, send email outreach.send_email
  catalogue import                    outreach.manage_templates

POST /api/public/enquiry is the website's server-to-server endpoint (same
contract as LeadMatch's, so the website only needs LEADMATCH_API_URL pointed
here). It requires the shared key in X-LeadMatch-Key
(MATCHMAKER_ENQUIRY_SECRET); without that key configured it refuses all calls.
"""
from __future__ import annotations

import csv
import hmac
import io
import ipaddress
import json
import logging
import os
import re
import time
from collections import defaultdict
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from backend.api.routes.access import check_access
from backend.api.routes.auth import current_username
from backend.api.routes.leads import _log_activity
from backend.database.connection import get_pool
from backend.services.activity_log import log_activity
from backend.services.ai_client import AIUnavailable, ai_configured
from backend.services.email_service import send_email, smtp_configured

from . import jobs
from . import repository as repo
from .db import Row, jsonable, loads, new_id, t
from .excel import build_catalogue_template, build_outbound_template, import_catalogue, parse_outbound_file
from .outreach import build_draft, international_number, personalize, requested_items
from .schemas import DraftIn, EnquiryIn, FeedbackIn, FollowUpIn, ProspectIn, SendEmailIn, WhatsAppLogIn
from .utils import digits_only, email_domain, normalize_company, normalize_domain

logger = logging.getLogger(__name__)
router = APIRouter()

FOLLOW_UP_STATUSES = {"new", "contacted", "in_discussion", "quoted", "not_relevant", "won", "lost"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_UPLOAD_ROWS = 2000


# --- permissions --------------------------------------------------------------

def require_any(*permissions: str, fresh: bool = False):
    """401 without a Lead Gen session, 403 without at least one of `permissions`."""

    def dependency(username: Optional[str] = Depends(current_username)) -> str:
        if not username:
            raise HTTPException(status_code=401, detail="Sign in through the Staff Portal.")
        access = check_access(username, fresh=fresh)
        if not any(access.can(p) for p in permissions):
            raise HTTPException(status_code=403, detail="You don't have permission to do this.")
        return username

    return dependency


VIEW = require_any("leads.generate", "leads.save")
ANALYSE = require_any("leads.generate")
UPDATE = require_any("leads.save")
EXPORT = require_any("leads.export")
OUTREACH = require_any("outreach.send_email")
MANAGE_CATALOGUE = require_any("outreach.manage_templates", fresh=True)


def default_country() -> str:
    return os.getenv("MATCHMAKER_DEFAULT_COUNTRY", "United Arab Emirates")


async def _pool():
    try:
        return await get_pool()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="The database is unavailable. Try again shortly.")


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = re.sub(r"[\u0000-\u0008\u000B\u000C\u000E-\u001F]", "", str(value)).strip()
    return text or None


# --- serializers ----------------------------------------------------------------

def _rec_out(r: Row) -> dict:
    primary = r.recommendation_type == "primary_requirement"
    return {
        "id": r.id,
        "product_id": r.product_id,
        "product_name": r.product_name,
        "division": r.division,
        "product_url": r.product_url,
        "applications": r.product_applications,
        "recommendation_type": r.recommendation_type,
        "is_primary": primary,
        "label": "Requested" if primary else ("Additional suggestion" if r.recommendation_type == "cross_sell" else "Potential fit - not yet verified"),
        "relevance_score": r.relevance_score,
        "confidence": r.confidence,
        "reason": r.reason,
        "activity": r.activity,
        "evidence_summary": r.evidence_summary,
        "evidence_url": r.evidence_url,
        "sales_verify": r.sales_verify,
        "feedback": r.feedback,
    }


def _lead_summary(l: Row) -> dict:
    return {
        "id": l.id,
        "lead_type": l.lead_type,
        "status": l.status,
        "follow_up_status": l.follow_up_status,
        "company_id": l.company_id,
        "company_name": l.company_name,
        "company_country": l.company_country,
        "company_industry": l.company_industry,
        "submitted_company_name": l.submitted_company_name,
        "contact_person": l.contact_person,
        "contact_email": l.contact_email,
        "contact_phone": l.contact_phone,
        "interested_division": l.interested_division,
        "interested_product": l.interested_product,
        "quantity": l.quantity,
        "external_reference": l.external_reference,
        "source": l.source,
        "primary_count": l.primary_count or 0,
        "suggestion_count": l.suggestion_count or 0,
        "error_message": l.error_message,
        "created_at": jsonable(l.created_at),
        "analysed_at": jsonable(l.analysed_at),
    }


def _warnings(lead: Row, company: Row, contacts: list[Row], primary: list, items: list[str], research: Row | None,
              searched_site: str | None = None) -> list[str]:
    """Missing or doubtful information sales should know about."""
    out = []
    email = lead.contact_email or next((c.email for c in contacts if c.email), None)
    phone = lead.contact_phone or next((c.whatsapp or c.phone for c in contacts if c.whatsapp or c.phone), None)
    if not email and not phone:
        out.append("No email or phone number on file: find a contact before outreach.")
    elif not phone:
        out.append("No phone number: WhatsApp is not available.")
    elif not 10 <= len(international_number(phone)) <= 15:
        out.append("The phone number looks incomplete (country code missing?). Check it before using WhatsApp.")
    if not email:
        out.append("No email address: email drafts are not available.")
    if searched_site:
        out.append(
            f"The website {searched_site} was found by a web search for the company name: "
            "confirm it is the same company before relying on the analysis."
        )
    if not company.website and not company.website_domain:
        out.append("No website or business email domain: the analysis used the details provided" + (" and a web search." if research and research.sources else " only."))
    elif research and not research.website_read and lead.status == "analysed":
        out.append("The company website could not be read: suggestions rely on the details provided.")
    if lead.lead_type == "inbound":
        if not (lead.interested_product or lead.interested_division or items):
            out.append("The enquiry names no product: confirm the requirement with the customer.")
        elif lead.status == "analysed" and not primary:
            out.append("The requested product was not matched to a catalogue line: check it manually.")
    if (company.name or "").endswith("(individual)"):
        out.append("Submitted without a company name (individual customer).")
    return out


async def _lead_detail(conn, lead_id: str) -> dict:
    lead = await repo.get_lead(conn, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    company = await repo.get_company(conn, lead.company_id)
    contacts = await repo.contacts_for(conn, company.id)
    research = await repo.latest_research(conn, company.id)
    recs = await repo.recommendations_for(conn, lead.id)
    primary = [_rec_out(r) for r in recs if r.recommendation_type == "primary_requirement"]
    suggestions = [_rec_out(r) for r in recs if r.recommendation_type != "primary_requirement"]
    items = requested_items(lead) if lead.lead_type == "inbound" else []
    history = await repo.outreach_history(conn, lead.id)
    lead_out = {k: jsonable(v) for k, v in lead.items()}
    lead_out["company_name"] = company.name
    return {
        "lead": lead_out,
        "company": {k: jsonable(v) for k, v in company.items()},
        "contacts": [{k: jsonable(v) for k, v in c.items()} for c in contacts],
        "research": {k: jsonable(v) for k, v in research.items()} if research else None,
        "requested_items": items,
        "requested": primary,
        "suggestions": suggestions,
        "warnings": _warnings(lead, company, contacts, primary, items, research, await repo.website_found_by_search(conn, company)),
        "outreach": [{k: jsonable(v) for k, v in h.items()} for h in history],
        "queued": jobs.is_queued(lead.id),
        "ai_configured": ai_configured(),
        "smtp_configured": smtp_configured(),
    }


# --- saving enquiries -----------------------------------------------------------

def _normalise_enquiry(p: EnquiryIn) -> dict:
    data = {k: _clean(v) if isinstance(v, str) else v for k, v in p.model_dump().items()}
    email = (data.get("business_email") or "").lower() or None
    phone = data.get("phone_number")
    if not email and not phone:
        raise HTTPException(status_code=422, detail="An email address or phone number is required.")
    if email and not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="business_email is not a valid email address.")
    if phone and len(digits_only(phone)) < 6:
        raise HTTPException(status_code=422, detail="phone_number is too short to be a phone number.")
    data["business_email"] = email
    contact = data.get("contact_person")
    if not data.get("company_name"):
        data["company_name"] = f"{contact} (individual)" if contact else (email or phone)
    data["contact_person"] = contact or "Website visitor"
    data["country"] = data.get("country") or default_country()
    if data.get("company_website") and not normalize_domain(data["company_website"]):
        data["company_website"] = None
    return data


async def save_enquiry(data: dict, created_by: Optional[str], default_source: str) -> tuple[Row, bool]:
    """Save company + contact + inbound lead. Returns (lead, duplicate)."""
    pool = await _pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Concurrent resends of the same website enquiry must not both insert.
            ref = data.get("external_reference")
            if ref:
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"mm-ref:{ref}")
                existing = await repo.lead_by_reference(conn, ref)
                if existing:
                    return existing, True
            else:
                existing = await repo.recent_duplicate_inbound(
                    conn, data.get("business_email"), data.get("phone_number"),
                    data.get("product_service"), data.get("requirement_description"),
                )
                if existing:
                    return existing, True
            company, _how = await repo.upsert_company(conn, {
                "name": data["company_name"],
                "website": data.get("company_website"),
                "email": data.get("business_email"),
                "city": data.get("city"),
                "country": data.get("country"),
                "industry": data.get("industry"),
                "source": data.get("source") or default_source,
            })
            await repo.upsert_contact(
                conn, company.id, person=data.get("contact_person"), email=data.get("business_email"),
                phone=data.get("phone_number"),
                whatsapp=data.get("phone_number") if data.get("whatsapp_same_as_phone") else None,
            )
            lead = await repo.create_lead(conn, company.id, {
                "lead_type": "inbound",
                "source": data.get("source") or default_source,
                "campaign": data.get("campaign"),
                "interested_division": data.get("interested_division"),
                "interested_product": data.get("product_service"),
                "quantity": data.get("quantity"),
                "application": data.get("application"),
                "technical_requirements": data.get("technical_requirements"),
                "timeline": data.get("timeline"),
                "requirement_description": data.get("requirement_description"),
                "additional_notes": data.get("additional_notes"),
                "utm_source": data.get("utm_source"),
                "utm_medium": data.get("utm_medium"),
                "utm_campaign": data.get("utm_campaign"),
                "utm_content": data.get("utm_content"),
                "utm_term": data.get("utm_term"),
                "landing_page": data.get("landing_page"),
                "referrer": data.get("referrer"),
                "form_version": data.get("form_version"),
                "external_reference": ref,
                "submitted_company_name": data["company_name"],
                "contact_person": data.get("contact_person"),
                "contact_email": data.get("business_email"),
                "contact_phone": data.get("phone_number"),
                "created_by": created_by,
            })
    return lead, False


# --- website enquiries (server to server) ----------------------------------------

_hits: dict[str, list[float]] = defaultdict(list)


def _enquiry_secret() -> str:
    return os.getenv("MATCHMAKER_ENQUIRY_SECRET") or os.getenv("PUBLIC_ENQUIRY_SECRET") or ""


def _rate_limit(key: str, limit: int, window: int = 60) -> None:
    now = time.monotonic()
    _hits[key] = [h for h in _hits[key] if now - h < window]
    if len(_hits[key]) >= limit:
        raise HTTPException(status_code=429, detail="Too many requests")
    _hits[key].append(now)


def _visitor_ip(request: Request) -> Optional[str]:
    try:
        return str(ipaddress.ip_address((request.headers.get("x-leadmatch-client-ip") or "").strip()))
    except ValueError:
        return None


@router.post("/api/public/enquiry")
@router.post("/api/matchmaker/public/enquiry")
async def public_enquiry(payload: EnquiryIn, request: Request):
    secret = _enquiry_secret()
    if not secret:
        logger.error("A website enquiry arrived but MATCHMAKER_ENQUIRY_SECRET is not set: refusing it.")
        raise HTTPException(status_code=503, detail="Website enquiries are not configured on this server")
    supplied = request.headers.get("x-leadmatch-key", "")
    if not hmac.compare_digest(supplied.encode(), secret.encode()):
        raise HTTPException(status_code=401, detail="Invalid or missing website key")
    if request.headers.get("x-leadmatch-hp"):
        raise HTTPException(status_code=400, detail="Rejected")
    visitor = _visitor_ip(request)
    limit = int(os.getenv("MATCHMAKER_ENQUIRY_RATE_LIMIT", "20") or 20)
    _rate_limit(f"enquiry|{visitor or 'site'}", limit if visitor else limit * 5)

    data = _normalise_enquiry(payload)
    lead, duplicate = await save_enquiry(data, None, "website_form")
    if duplicate:
        return {"ok": True, "lead_id": lead.id, "message": "Enquiry already received", "duplicate": True}
    jobs.enqueue(lead.id)
    # Not a staff action: attributed to the website, not to a signed-in user.
    log_activity("website", "matchmaker.enquiry_received", entity_type="matchmaker_lead", entity_id=lead.id,
                 metadata={"source": lead.source, "reference": lead.external_reference})
    return JSONResponse(status_code=201, content={"ok": True, "lead_id": lead.id, "message": "Enquiry received"})


# --- team: leads ----------------------------------------------------------------

@router.get("/api/matchmaker/summary")
async def summary(user: str = Depends(VIEW)):
    pool = await _pool()
    async with pool.acquire() as conn:
        s = await repo.stats(conn)
        recent, _ = await repo.list_leads(conn, None, None, None, 1, 8)
    return {
        **{k: int(v or 0) for k, v in s.items()},
        "recent": [_lead_summary(l) for l in recent],
        "ai_configured": ai_configured(),
        "website_enquiries_configured": bool(_enquiry_secret()),
    }


@router.get("/api/matchmaker/leads")
async def list_leads(
    type: Optional[str] = Query(None, pattern="^(inbound|outbound)$"),
    status: Optional[str] = Query(None, pattern="^(pending|researching|analysed|failed)$"),
    q: Optional[str] = Query(None, max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: str = Depends(VIEW),
):
    pool = await _pool()
    async with pool.acquire() as conn:
        items, total = await repo.list_leads(conn, type, status, q, page, page_size)
    return {"items": [_lead_summary(l) for l in items], "total": total, "page": page, "page_size": page_size}


@router.get("/api/matchmaker/leads/{lead_id}")
async def get_lead(lead_id: str, user: str = Depends(VIEW)):
    pool = await _pool()
    async with pool.acquire() as conn:
        return await _lead_detail(conn, lead_id)


@router.post("/api/matchmaker/inbound")
async def create_inbound(payload: EnquiryIn, request: Request, user: str = Depends(ANALYSE)):
    """An enquiry received by phone, email or in person, typed in by sales."""
    data = _normalise_enquiry(payload)
    lead, duplicate = await save_enquiry(data, user, data.get("source") or "manual")
    if not duplicate:
        jobs.enqueue(lead.id)
        _log_activity(request, "matchmaker.inbound_created", entity_type="matchmaker_lead", entity_id=lead.id)
    return {
        "lead_id": lead.id,
        "duplicate": duplicate,
        "status": lead.status,
        "message": "This enquiry is already saved." if duplicate else "Enquiry saved. Analysis is running in the background.",
    }


async def _save_prospect(conn, row_in: dict, created_by: str, batch_id: Optional[str] = None) -> tuple[Row, str]:
    """Upsert company + contact; reuse its outbound lead if it is already a prospect.
    Returns (lead, "new" | "existing_prospect" | "existing_company")."""
    company, how = await repo.upsert_company(conn, {
        "name": row_in["company_name"],
        "website": row_in.get("website"),
        "email": row_in.get("email"),
        "city": row_in.get("city"),
        "country": row_in.get("country") or default_country(),
        "industry": row_in.get("industry"),
        "description": row_in.get("description"),
        "notes": row_in.get("notes"),
        "source": row_in.get("source") or ("outbound_upload" if batch_id else "manual"),
    })
    await repo.upsert_contact(
        conn, company.id, person=row_in.get("contact_person"), email=row_in.get("email"), phone=row_in.get("phone"),
        whatsapp=row_in.get("whatsapp") or row_in.get("phone"), designation=row_in.get("designation"),
        verified=bool(row_in.get("email") or row_in.get("phone")),
    )
    existing = await repo.outbound_lead_for_company(conn, company.id)
    if existing:
        return existing, "existing_prospect"
    lead = await repo.create_lead(conn, company.id, {
        "lead_type": "outbound",
        "source": row_in.get("source") or ("outbound_upload" if batch_id else "manual"),
        "additional_notes": row_in.get("notes"),
        "submitted_company_name": row_in["company_name"],
        "contact_person": row_in.get("contact_person"),
        "contact_email": (row_in.get("email") or "").lower() or None,
        "contact_phone": row_in.get("phone"),
        "batch_id": batch_id,
        "created_by": created_by,
    })
    return lead, ("existing_company" if how != "new" else "new")


def _prospect_dict(p: ProspectIn) -> dict:
    data = {k: _clean(v) if isinstance(v, str) else v for k, v in p.model_dump().items()}
    if not data.get("company_name"):
        raise HTTPException(status_code=422, detail="Company name is required.")
    if data.get("email") and not EMAIL_RE.match(data["email"]):
        raise HTTPException(status_code=422, detail="The email address is not valid.")
    if data.get("website") and not normalize_domain(data["website"]):
        data["website"] = None
    return data


@router.post("/api/matchmaker/outbound")
async def create_outbound(payload: ProspectIn, request: Request, user: str = Depends(ANALYSE)):
    data = _prospect_dict(payload)
    pool = await _pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"mm-prospect:{normalize_company(data['company_name'])}")
            lead, outcome = await _save_prospect(conn, data, user)
    duplicate = outcome == "existing_prospect"
    if not duplicate:
        jobs.enqueue(lead.id)
        _log_activity(request, "matchmaker.prospect_created", entity_type="matchmaker_lead", entity_id=lead.id)
    return {
        "lead_id": lead.id,
        "duplicate": duplicate,
        "message": (
            "This company is already a prospect: its details were updated. Open it to re-run the analysis."
            if duplicate else "Prospect saved. Analysis is running in the background."
        ),
    }


@router.get("/api/matchmaker/outbound/template")
async def outbound_template(user: str = Depends(VIEW)):
    return StreamingResponse(
        io.BytesIO(build_outbound_template()),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Outbound_Prospects_Template.xlsx"},
    )


def _upload_row(r: dict) -> dict:
    return {
        "company_name": _clean(r.get("Company_Name")),
        "country": _clean(r.get("Country")),
        "website": _clean(r.get("Website")),
        "industry": _clean(r.get("Industry")),
        "city": _clean(r.get("City")),
        "description": _clean(r.get("Company_Description")),
        "contact_person": _clean(r.get("Contact_Person")),
        "designation": _clean(r.get("Designation")),
        "email": (_clean(r.get("Business_Email")) or "").lower() or None,
        "phone": _clean(r.get("Business_Phone")),
        "whatsapp": _clean(r.get("WhatsApp_Number")),
        "notes": _clean(r.get("Notes")),
        "source": _clean(r.get("Source")),
    }


@router.post("/api/matchmaker/outbound/preview")
async def outbound_preview(request: Request, file: UploadFile = File(...), user: str = Depends(ANALYSE)):
    name = file.filename or ""
    if not name.lower().endswith((".xlsx", ".xlsm", ".csv")):
        raise HTTPException(status_code=400, detail="Upload an Excel (.xlsx) or CSV file.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="The file is too large (max 12 MB).")
    try:
        parsed = parse_outbound_file(content, name)
    except Exception as exc:  # noqa: BLE001 -- corrupt or unexpected files
        logger.info("Outbound upload could not be read: %s", type(exc).__name__)
        raise HTTPException(status_code=400, detail="The file could not be read. Use the template's format.")
    if not parsed:
        raise HTTPException(status_code=400, detail="No rows found. The first row must be headers, with a Company_Name column.")
    if len(parsed) > MAX_UPLOAD_ROWS:
        raise HTTPException(status_code=400, detail=f"Too many rows ({len(parsed)}); upload at most {MAX_UPLOAD_ROWS} at a time.")

    preview, seen = [], {}
    counts = {"new": 0, "existing": 0, "duplicate": 0, "invalid": 0}
    pool = await _pool()
    async with pool.acquire() as conn:
        for i, raw in enumerate(parsed, 2):
            item = _upload_row(raw)
            entry = {"row": i, **item, "warnings": []}
            if not item["company_name"]:
                entry.update(status="invalid", reason="Company_Name is missing")
            elif item["email"] and not EMAIL_RE.match(item["email"]):
                entry.update(status="invalid", reason="Business_Email is not a valid email address")
            else:
                key = normalize_domain(item["website"]) or email_domain(item["email"]) or normalize_company(item["company_name"])
                if key in seen:
                    entry.update(status="duplicate", reason=f"Same company as row {seen[key]} in this file")
                else:
                    seen[key] = i
                    company, how = await repo.find_company(
                        conn, item["company_name"], item["website"], item["email"], item["city"], item["country"] or default_country()
                    )
                    prospect = await repo.outbound_lead_for_company(conn, company.id) if company else None
                    if prospect:
                        entry.update(status="existing", reason="Already a prospect: details will be merged, no new lead", lead_id=prospect.id)
                    elif company:
                        entry.update(status="new", reason=f"Known company (matched by {how.replace('_', ' ')})")
                    else:
                        entry.update(status="new")
                if not item["country"]:
                    entry["warnings"].append(f"No country: {default_country()} assumed")
                if not item["website"] and not email_domain(item["email"]):
                    entry["warnings"].append("No website or business email: the company will be looked up by name")
            counts["existing" if entry["status"] == "existing" else entry["status"]] += 1
            preview.append(entry)
        batch_id = new_id("BAT")
        await conn.execute(
            f"""INSERT INTO {t('batches')} (id, filename, status, total_rows, new_count, existing_count, duplicate_count,
                    invalid_count, preview, created_by) VALUES ($1,$2,'preview',$3,$4,$5,$6,$7,$8::jsonb,$9)""",
            batch_id, name[:255], len(parsed), counts["new"], counts["existing"], counts["duplicate"], counts["invalid"],
            json.dumps(preview), user,
        )
    return {"batch_id": batch_id, "filename": name, "total": len(parsed), **counts, "rows": preview[:500]}


@router.post("/api/matchmaker/outbound/batches/{batch_id}/confirm")
async def outbound_confirm(batch_id: str, request: Request, user: str = Depends(ANALYSE)):
    pool = await _pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            batch = await conn.fetchrow(f"SELECT * FROM {t('batches')} WHERE id = $1 FOR UPDATE", batch_id)
            if not batch:
                raise HTTPException(status_code=404, detail="Upload not found")
            if batch["status"] != "preview":
                raise HTTPException(status_code=409, detail="This upload was already imported.")
            await conn.execute(f"UPDATE {t('batches')} SET status = 'processing', updated_at = now() WHERE id = $1", batch_id)
        preview = loads(batch["preview"], [])
        to_analyse, created, merged, failed = [], 0, 0, 0
        for entry in preview:
            if entry.get("status") not in {"new", "existing"}:
                continue
            try:
                async with conn.transaction():
                    lead, outcome = await _save_prospect(conn, entry, user, batch_id)
                if outcome == "existing_prospect":
                    merged += 1
                else:
                    created += 1
                    to_analyse.append(lead.id)
            except Exception as exc:  # noqa: BLE001 -- one bad row must not stop the batch
                failed += 1
                logger.warning("Outbound row %s failed: %s", entry.get("row"), type(exc).__name__)
        await conn.execute(
            f"UPDATE {t('batches')} SET status = 'completed', processed_count = $2, failed_count = $3, updated_at = now() WHERE id = $1",
            batch_id, created + merged, failed,
        )
    for lead_id in to_analyse:
        jobs.enqueue(lead_id)
    _log_activity(request, "matchmaker.prospects_imported", entity_type="matchmaker_batch", entity_id=batch_id,
                  metadata={"created": created, "merged": merged, "failed": failed})
    return {"batch_id": batch_id, "created": created, "merged": merged, "failed": failed,
            "message": f"{created} prospect{'' if created == 1 else 's'} added and queued for analysis" + (f", {merged} already existed" if merged else "") + (f", {failed} failed" if failed else "") + "."}


@router.get("/api/matchmaker/outbound/batches")
async def list_batches(user: str = Depends(VIEW)):
    pool = await _pool()
    async with pool.acquire() as conn:
        items = await conn.fetch(
            f"""SELECT id, filename, status, total_rows, new_count, existing_count, duplicate_count, invalid_count,
                       processed_count, failed_count, created_by, created_at FROM {t('batches')}
                ORDER BY created_at DESC LIMIT 20"""
        )
    return [{k: jsonable(v) for k, v in dict(r).items()} for r in items]


@router.post("/api/matchmaker/leads/{lead_id}/reanalyse")
async def reanalyse(lead_id: str, request: Request, user: str = Depends(ANALYSE)):
    pool = await _pool()
    async with pool.acquire() as conn:
        lead = await repo.get_lead(conn, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        if jobs.is_queued(lead_id):
            return {"lead_id": lead_id, "status": "researching", "message": "The analysis is already running."}
        await conn.execute(f"UPDATE {t('leads')} SET status = 'pending', error_message = NULL, attempts = 0 WHERE id = $1", lead_id)
    jobs.enqueue(lead_id, force_research=True)
    _log_activity(request, "matchmaker.reanalysed", entity_type="matchmaker_lead", entity_id=lead_id)
    return {"lead_id": lead_id, "status": "pending", "message": "Analysis restarted."}


@router.patch("/api/matchmaker/leads/{lead_id}/follow-up")
async def follow_up(lead_id: str, payload: FollowUpIn, request: Request, user: str = Depends(UPDATE)):
    if payload.follow_up_status not in FOLLOW_UP_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid follow-up status")
    pool = await _pool()
    async with pool.acquire() as conn:
        done = await conn.execute(
            f"UPDATE {t('leads')} SET follow_up_status = $2, updated_at = now() WHERE id = $1", lead_id, payload.follow_up_status
        )
    if done.endswith(" 0"):
        raise HTTPException(status_code=404, detail="Lead not found")
    _log_activity(request, "matchmaker.follow_up_changed", entity_type="matchmaker_lead", entity_id=lead_id,
                  metadata={"to": payload.follow_up_status})
    return {"lead_id": lead_id, "follow_up_status": payload.follow_up_status}


@router.post("/api/matchmaker/recommendations/{rec_id}/feedback")
async def feedback(rec_id: str, payload: FeedbackIn, request: Request, user: str = Depends(UPDATE)):
    if payload.verdict not in {"relevant", "irrelevant", ""}:
        raise HTTPException(status_code=400, detail="Verdict must be relevant or irrelevant")
    pool = await _pool()
    async with pool.acquire() as conn:
        done = await conn.execute(
            f"UPDATE {t('recommendations')} SET feedback = $2, feedback_by = $3 WHERE id = $1",
            rec_id, payload.verdict or None, user,
        )
    if done.endswith(" 0"):
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return {"id": rec_id, "feedback": payload.verdict or None}


# --- team: outreach drafts ------------------------------------------------------

def _pick_contact(lead: Row, contacts: list[Row]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """(name, email, phone) of the person to write to: the enquirer first, then a company contact."""
    name, email, phone = lead.contact_person, lead.contact_email, lead.contact_phone
    for c in contacts:
        if not email and c.email:
            email, name = c.email, name or c.contact_person
        if not phone and (c.whatsapp or c.phone):
            phone, name = c.whatsapp or c.phone, name or c.contact_person
    return name, email, phone


@router.post("/api/matchmaker/leads/{lead_id}/drafts")
async def drafts(lead_id: str, payload: DraftIn, request: Request, user: str = Depends(OUTREACH)):
    pool = await _pool()
    async with pool.acquire() as conn:
        lead = await repo.get_lead(conn, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        company = await repo.get_company(conn, lead.company_id)
        contacts = await repo.contacts_for(conn, company.id)
        research = await repo.latest_research(conn, company.id)
        recs = await repo.recommendations_for(conn, lead.id)

    def as_product(r: Row) -> Row:
        return Row(id=r.product_id, name=r.product_name, description=r.product_description, applications=r.product_applications)

    chosen = set(payload.recommendation_ids)
    unknown = chosen - {r.id for r in recs}
    if unknown:
        raise HTTPException(status_code=400, detail="Some chosen suggestions do not belong to this lead.")
    primary = [as_product(r) for r in recs if r.recommendation_type == "primary_requirement"]
    picked = [as_product(r) for r in recs if r.id in chosen and r.recommendation_type != "primary_requirement"]
    if lead.lead_type == "outbound" and not picked:
        # An introduction needs something to introduce: default to the best fits.
        picked = [as_product(r) for r in recs if r.feedback != "irrelevant"][:2]

    name, email, phone = _pick_contact(lead, contacts)
    agent = _signed_in_name(request)
    draft = build_draft(company, lead, primary, picked, name, agent, research)

    ai_error = None
    if payload.personalize:
        facts = {
            "customer_company": company.name,
            "contact_name": name,
            "company_industry": company.industry,
            "company_summary": research.summary if research else company.description,
            "company_activities": research.business_activities if research else None,
            "enquiry_reference": lead.external_reference,
            "requested_items": requested_items(lead),
            "quantity": lead.quantity,
            "customer_message": lead.requirement_description,
            "products_to_mention": [{"name": p.name, "description": p.description, "uses": p.applications} for p in primary + picked],
            "sender_name": agent,
        }
        try:
            draft = await personalize(draft, facts)
        except AIUnavailable as exc:
            ai_error = f"AI personalisation unavailable ({exc}); showing the standard draft."

    number = international_number(phone)
    whatsapp = (
        {
            "available": True, "number": number, "message": draft.whatsapp,
            "url": f"https://wa.me/{number}?text={quote(draft.whatsapp)}",
            "warning": None if 10 <= len(number) <= 15 else f"+{number} looks incomplete (missing country code?). Check it before sending.",
        }
        if number else {"available": False, "message": draft.whatsapp, "reason": "No phone or WhatsApp number on file. Do not invent numbers."}
    )
    email_out = (
        {
            "available": True, "recipient": email, "subject": draft.subject, "body": draft.email,
            "mailto": f"mailto:{email}?subject={quote(draft.subject)}&body={quote(draft.email)}",
        }
        if email else {"available": False, "subject": draft.subject, "body": draft.email, "reason": "No email address on file. Do not invent addresses."}
    )
    return {
        "situation": draft.situation,
        "personalized": draft.personalized,
        "ai_error": ai_error,
        "contact_name": name,
        "products": [p.name for p in primary + picked],
        "whatsapp": whatsapp,
        "email": email_out,
        "smtp_configured": smtp_configured(),
        "note": "Review and edit before sending. Opening WhatsApp does not send the message.",
    }


def _signed_in_name(request: Request) -> str:
    """The signed-in person's display name from the Lead Gen session, for signatures."""
    import jwt

    from backend.api.routes.auth import SESSION_COOKIE_NAME, _session_secret

    token = request.cookies.get(SESSION_COOKIE_NAME)
    try:
        claims = jwt.decode(token, _session_secret(), algorithms=["HS256"]) if token else {}
    except Exception:  # noqa: BLE001
        claims = {}
    name = claims.get("name")
    return name if isinstance(name, str) and name.strip() else ""


@router.post("/api/matchmaker/leads/{lead_id}/send-email")
async def send_lead_email(lead_id: str, payload: SendEmailIn, request: Request, user: str = Depends(OUTREACH)):
    if not smtp_configured():
        raise HTTPException(status_code=503, detail="SMTP not configured")
    recipient = payload.recipient.strip().lower()
    if not EMAIL_RE.match(recipient):
        raise HTTPException(status_code=422, detail="The recipient is not a valid email address.")
    pool = await _pool()
    async with pool.acquire() as conn:
        lead = await repo.get_lead(conn, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
    result = await send_email(recipient, payload.subject, payload.body)
    status = "sent" if result["success"] else "failed"
    async with pool.acquire() as conn:
        await repo.log_outreach(conn, lead.id, lead.company_id, "email", recipient, payload.subject, status, result.get("error"), user)
        if result["success"] and lead.follow_up_status == "new":
            await conn.execute(f"UPDATE {t('leads')} SET follow_up_status = 'contacted', updated_at = now() WHERE id = $1", lead.id)
    _log_activity(request, "matchmaker.email_sent" if result["success"] else "matchmaker.email_failed",
                  entity_type="matchmaker_lead", entity_id=lead.id,
                  metadata={"subject": payload.subject, "recipientDomain": recipient.rsplit("@", 1)[-1]})
    if not result["success"]:
        return {"success": False, "error": result.get("error") or "Sending failed"}
    return {"success": True}


@router.post("/api/matchmaker/leads/{lead_id}/whatsapp-opened")
async def whatsapp_opened(lead_id: str, payload: WhatsAppLogIn, request: Request, user: str = Depends(OUTREACH)):
    """Record that sales opened the WhatsApp draft (the message itself is sent from WhatsApp)."""
    pool = await _pool()
    async with pool.acquire() as conn:
        lead = await repo.get_lead(conn, lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        await repo.log_outreach(conn, lead.id, lead.company_id, "whatsapp", digits_only(payload.number), None, "opened", None, user)
        if lead.follow_up_status == "new":
            await conn.execute(f"UPDATE {t('leads')} SET follow_up_status = 'contacted', updated_at = now() WHERE id = $1", lead.id)
    _log_activity(request, "matchmaker.whatsapp_opened", entity_type="matchmaker_lead", entity_id=lead_id)
    return {"ok": True}


# --- team: catalogue --------------------------------------------------------------

@router.get("/api/matchmaker/catalogue")
async def catalogue(q: Optional[str] = Query(None, max_length=200), include_inactive: bool = False, user: str = Depends(VIEW)):
    pool = await _pool()
    async with pool.acquire() as conn:
        params, where = [], [] if include_inactive else ["p.is_active", "d.is_active"]
        if q:
            params.append(f"%{q.strip()}%")
            where.append(f"(p.name ILIKE $1 OR d.name ILIKE $1 OR p.target_industries ILIKE $1 OR p.applications ILIKE $1)")
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        items = await conn.fetch(
            f"""SELECT p.id, p.name, p.category, p.applications, p.target_industries, p.service_area, p.is_active,
                       p.product_url, d.name AS division, d.is_active AS division_active
                FROM {t('products')} p JOIN {t('divisions')} d ON d.id = p.division_id {clause}
                ORDER BY d.name, p.name LIMIT 1000""",
            *params,
        )
        divisions = await conn.fetchval(f"SELECT count(*) FROM {t('divisions')} WHERE is_active")
    return {"divisions": divisions, "items": [dict(r) for r in items]}


@router.get("/api/matchmaker/catalogue/template")
async def catalogue_template(user: str = Depends(VIEW)):
    return StreamingResponse(
        io.BytesIO(build_catalogue_template()),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Product_Catalogue_Template.xlsx"},
    )


@router.post("/api/matchmaker/catalogue/import")
async def catalogue_import(request: Request, file: UploadFile = File(...), user: str = Depends(MANAGE_CATALOGUE)):
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Upload an Excel .xlsx file.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="The file is too large (max 12 MB).")
    pool = await _pool()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                result = await import_catalogue(conn, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Catalogue import failed: %s", type(exc).__name__)
        raise HTTPException(status_code=400, detail="The workbook could not be imported. Use the template's format.")
    _log_activity(request, "matchmaker.catalogue_imported", entity_type="matchmaker_catalogue",
                  metadata={"fileName": file.filename, **{k: v for k, v in result.items() if k != "errors"}, "errors": len(result["errors"])})
    return result


# --- team: export -------------------------------------------------------------------

@router.get("/api/matchmaker/export/leads.csv")
async def export_leads(type: Optional[str] = Query(None, pattern="^(inbound|outbound)$"), user: str = Depends(EXPORT)):
    pool = await _pool()
    async with pool.acquire() as conn:
        items = await conn.fetch(
            f"""SELECT l.id, l.lead_type, l.status, l.follow_up_status, l.external_reference, c.name AS company, c.country,
                       c.industry, l.contact_person, l.contact_email, l.contact_phone, l.interested_product, l.created_at,
                       string_agg(CASE WHEN r.recommendation_type = 'primary_requirement' THEN p.name END, '; ') AS requested,
                       string_agg(CASE WHEN r.recommendation_type <> 'primary_requirement' THEN p.name || ' (' || r.confidence || ')' END, '; ') AS suggestions
                FROM {t('leads')} l JOIN {t('companies')} c ON c.id = l.company_id
                LEFT JOIN {t('recommendations')} r ON r.lead_id = l.id
                LEFT JOIN {t('products')} p ON p.id = r.product_id
                WHERE ($1::text IS NULL OR l.lead_type = $1)
                GROUP BY l.id, c.id ORDER BY l.created_at DESC""",
            type,
        )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Lead ID", "Type", "Status", "Follow-up", "Website ref", "Company", "Country", "Industry", "Contact",
                     "Email", "Phone", "Asked for", "Requested lines", "Suggestions", "Created"])
    for r in items:
        values = [r["id"], r["lead_type"], r["status"], r["follow_up_status"], r["external_reference"], r["company"],
                  r["country"], r["industry"], r["contact_person"], r["contact_email"], r["contact_phone"],
                  r["interested_product"], r["requested"], r["suggestions"], jsonable(r["created_at"])]
        # Neutralise spreadsheet formulas in user-supplied text.
        writer.writerow([("'" + v) if isinstance(v, str) and v[:1] in "=+-@" else (v or "") for v in values])
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lead_matchmaker_leads.csv"},
    )
