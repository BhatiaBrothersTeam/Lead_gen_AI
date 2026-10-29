import json
import io
import logging
import pandas as pd
import asyncio
from typing import Optional, List
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from backend.models.lead_models import (
    LeadsRequest, GenerateLeadsInput, SingleEmailRequest, BulkEmailRequest, EmailTemplateSchema
)
import backend.services.database as db_service
from backend.services.product_analyzer import analyze_product
from backend.services.company_discovery import discover_companies
from backend.services.lead_extractor import extract_leads
from backend.services.lead_enricher import enrich_leads
from backend.services.lead_validator import validate_leads
from backend.services.email_service import verify_smtp_connection, send_email, smtp_configured
from backend.services.activity_log import log_activity
from backend.api.routes.auth import session_user_id
from backend.api.routes.access import require_permission

logger = logging.getLogger(__name__)
router = APIRouter()

# Every route needs a Lead Gen permission from the Staff Portal's access
# registry (401 without a session, 403 without the permission). The keys match
# the permissions the portal seeds for "LGA"; roles are mapped to them there.
LEADS_GENERATE = Depends(require_permission("leads.generate"))
LEADS_SAVE = Depends(require_permission("leads.save"))
SEND_EMAIL = Depends(require_permission("outreach.send_email"))
# Bulk email is the most sensitive action, so it always asks the portal fresh.
SEND_BULK = Depends(require_permission("outreach.send_bulk", fresh=True))
MANAGE_TEMPLATES = Depends(require_permission("outreach.manage_templates"))
TEST_SMTP = Depends(require_permission("outreach.test_smtp"))

# How many lead ids to keep in one activity-log entry's metadata.
MAX_LOGGED_IDS = 100


def _require_smtp() -> None:
    """503 instead of a send attempt when the SMTP credentials aren't set."""
    if not smtp_configured():
        raise HTTPException(status_code=503, detail="SMTP not configured")


def _log_activity(request: Request, action: str, **kwargs) -> None:
    """
    Reports a user action to the Staff Portal's activity log, attributed to the
    SSO-signed-in user. Fire-and-forget: never blocks or fails the endpoint.
    See backend/services/activity_log.py.
    """
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    log_activity(
        session_user_id(request) or "anonymous",
        action,
        ip_address=forwarded or (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        **kwargs,
    )

@router.get("/api/product-service-types", dependencies=[LEADS_GENERATE])
async def get_product_service_types(category: Optional[str] = Query(None)):
    """
    Returns product service types optionally filtered by category.
    """
    try:
        types = await db_service.get_product_service_types(category)
        return {"types": types}
    except Exception as e:
        logger.error(f"Failed to fetch product service types: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch types")


@router.get("/api/product-service-names", dependencies=[LEADS_GENERATE])
async def get_product_service_names(typeId: int, category: str):
    """
    Returns product service names for a given type and category.
    """
    try:
        names = await db_service.get_product_service_names(typeId, category)
        return {"names": names}
    except Exception as e:
        logger.error(f"Failed to fetch product service names: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch names")


@router.post("/api/upload-file", dependencies=[LEADS_GENERATE])
async def upload_file(request: Request, file: UploadFile = File(...)):
    """
    Uploads and parses an Excel file containing product listings.
    """
    try:
        contents = await file.read()
        # Read Excel spreadsheet using pandas
        df = pd.read_excel(io.BytesIO(contents))
        
        products = []
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            product_name = row_dict.get('post_title') or row_dict.get('product_name') or row_dict.get('Name') or ""
            sku = row_dict.get('SKU') or row_dict.get('sku') or ""
            brand = row_dict.get('Brand') or row_dict.get('brand') or ""
            
            # Handle potential NaN values from pandas
            if pd.isna(product_name): product_name = ""
            if pd.isna(sku): sku = ""
            if pd.isna(brand): brand = ""
            
            product_name = str(product_name).strip()
            sku = str(sku).strip()
            brand = str(brand).strip()
            
            if product_name:
                products.append({
                    "product_name": product_name,
                    "sku": sku,
                    "brand": brand
                })

        _log_activity(
            request,
            "products.imported",
            entity_type="product_file",
            metadata={"fileName": file.filename, "products": len(products)},
        )
        return {"products": products}
    except Exception as e:
        logger.error(f"Error processing uploaded file: {e}")
        raise HTTPException(status_code=500, detail="Failed to process Excel file")


@router.post("/api/filter-existing-leads", dependencies=[LEADS_SAVE])
async def filter_existing_leads(request: LeadsRequest):
    """
    Filters out leads that already exist in the database.
    """
    try:
        # Convert pydantic models to dictionaries
        leads_dict = [l.model_dump(by_alias=True) for l in request.leads]
        unique_leads = await db_service.filter_existing_leads(leads_dict)
        return {"uniqueLeads": unique_leads}
    except Exception as e:
        logger.error(f"Error filtering leads: {e}")
        raise HTTPException(status_code=500, detail="Failed to filter leads")


@router.post("/api/save-leads", dependencies=[LEADS_SAVE])
async def save_leads(request: LeadsRequest, http_request: Request):
    """
    Saves a batch of leads directly into the database.
    """
    try:
        # Convert pydantic models to dictionaries
        leads_dict = [l.model_dump(by_alias=True) for l in request.leads]
        res = await db_service.save_leads_directly(leads_dict)

        lead_ids = [l.get("id") for l in res.get("leads", []) if l.get("id") is not None]
        _log_activity(
            http_request,
            "lead.created",
            entity_type="lead",
            entity_id=lead_ids[0] if len(lead_ids) == 1 else None,
            metadata={
                "count": len(lead_ids),
                "leadIds": lead_ids[:MAX_LOGGED_IDS],
                "divisions": sorted({(l.get("division") or "Not Specified") for l in leads_dict}),
            },
        )
        return res
    except Exception as e:
        logger.error(f"Error saving leads: {e}")
        raise HTTPException(status_code=500, detail="Failed to save leads")


@router.post("/api/generate-leads", dependencies=[LEADS_GENERATE])
async def generate_leads(input_data: GenerateLeadsInput, request: Request):
    """
    Core pipeline generator using Server-Sent Events (SSE).
    """
    async def event_generator():
        def make_event(status: str, message: str, **kwargs):
            return f"data: {json.dumps({'status': status, 'message': message, **kwargs})}\n\n"

        try:
            product_name = input_data.productName
            brand = input_data.brand
            division = (input_data.division or "").strip() or "Not Specified"
            description = input_data.description

            if not product_name or product_name.strip() == "":
                yield make_event("error", "Product name is required.")
                return

            # Step 1: Product Analysis
            yield make_event("analyzing", "Analyzing Product...")
            try:
                analysis = await analyze_product(
                    division=division,
                    product_name=product_name,
                    brand=brand,
                    description=description
                )
                logger.info(f"Product analysis completed: {analysis}")
            except Exception as e:
                logger.error(f"Product analysis failed: {e}")
                yield make_event("error", f"Product analysis failed: {str(e)}")
                return

            # Determine keywords
            keywords = analysis.get("searchKeywords") or analysis.get("keywords") or []
            if not keywords:
                keywords = [f"{product_name} supplier Dubai"]

            # Step 2: Company Discovery
            yield make_event("searching", "Finding Companies...")
            try:
                search_results = await discover_companies(keywords)
                logger.info(f"Company discovery completed: found {len(search_results)} search results")
            except Exception as e:
                logger.error(f"Company discovery failed: {e}")
                yield make_event("error", f"Company discovery failed: {str(e)}")
                return

            if not search_results:
                yield make_event("error", "No companies found from search results.")
                return

            # Step 3: Lead Extraction
            yield make_event("extracting", "Extracting Leads...")
            try:
                extracted_leads = await extract_leads(search_results)
                logger.info(f"Lead extraction completed: extracted {len(extracted_leads)} leads")
            except Exception as e:
                logger.error(f"Lead extraction failed: {e}")
                yield make_event("error", f"Lead extraction failed: {str(e)}")
                return

            if not extracted_leads:
                yield make_event("error", "No leads could be extracted from search results.")
                return

            # Step 4: Lead Enrichment
            yield make_event("enriching", "Enriching Leads with Contact Details...")
            
            # SSE progress callback queue logic
            queue = asyncio.Queue()
            def sync_callback(msg: str):
                queue.put_nowait(msg)

            async def enrichment_worker():
                try:
                    return await enrich_leads(extracted_leads, sync_callback)
                finally:
                    # Signal that the enrichment is done
                    await queue.put(None)

            # Start enrichment in a background task
            enrichment_task = asyncio.create_task(enrichment_worker())

            # Read logs from queue and yield them to clients
            while True:
                msg = await queue.get()
                if msg is None:
                    break
                yield make_event("enriching", msg)

            enriched_leads = await enrichment_task
            logger.info(f"Lead enrichment completed: enriched {len(enriched_leads)} leads")

            # Step 5: Lead Validation
            yield make_event("validating", "Validating Leads...")
            try:
                validated_leads = validate_leads(enriched_leads)
                logger.info(f"Lead validation completed: {len(validated_leads)} valid leads remaining")
            except Exception as e:
                logger.error(f"Lead validation failed: {e}")
                yield make_event("error", f"Lead validation failed: {str(e)}")
                return

            if not validated_leads:
                yield make_event("error", "All discovered leads failed validation checks.")
                return

            # Step 6: Save to database (Upserts & partial field matching)
            yield make_event("saving", "Saving Leads...")
            try:
                for lead in validated_leads:
                    lead["division"] = division
                db_result = await db_service.save_or_update_leads(validated_leads)
                logger.info(f"Database save completed: {db_result}")
            except Exception as e:
                logger.error(f"Database save failed: {e}")
                yield make_event("error", f"Database save failed: {str(e)}")
                return

            # One entry per run (not per lead): new and updated leads are counted.
            _log_activity(
                request,
                "leads.generated",
                entity_type="lead",
                metadata={
                    "productName": product_name,
                    "brand": brand,
                    "division": division,
                    "totalFound": db_result.get("totalFound") or 0,
                    "newLeadsAdded": db_result.get("newLeadsAdded") or 0,
                    "existingLeadsUpdated": db_result.get("existingLeadsUpdated") or 0,
                    "duplicatesSkipped": db_result.get("duplicatesSkipped") or 0,
                },
            )

            # Yield final completion summary
            yield make_event(
                "completed", 
                "Leads generation completed successfully!",
                leads=db_result.get("leads") or [],
                stats={
                    "totalFound": db_result.get("totalFound") or 0,
                    "newLeadsAdded": db_result.get("newLeadsAdded") or 0,
                    "existingLeadsUpdated": db_result.get("existingLeadsUpdated") or 0,
                    "duplicatesSkipped": db_result.get("duplicatesSkipped") or 0,
                }
            )

        except Exception as e:
            logger.error(f"Generate leads pipeline exception: {e}")
            yield make_event("error", f"An unexpected pipeline error occurred: {str(e)}")

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/api/test-smtp", dependencies=[TEST_SMTP])
async def test_smtp():
    """
    Verify SMTP credentials and connect to the SMTP server.
    """
    _require_smtp()
    res = await verify_smtp_connection()
    return res


@router.post("/api/send-email", dependencies=[SEND_EMAIL])
async def send_single_email(req: SingleEmailRequest, request: Request):
    """
    Sends a single email and returns success status.
    """
    _require_smtp()
    res = await send_email(req.email, req.subject, req.body)
    logger.info(f"Single email send to {req.email} result: {res}")

    # Only the recipient's domain goes to the central log, not the address.
    _log_activity(
        request,
        "email.sent" if res["success"] else "email.failed",
        entity_type="email",
        metadata={
            "subject": req.subject,
            "recipientDomain": req.email.rsplit("@", 1)[-1] if "@" in req.email else None,
        },
    )

    if res["success"]:
        return {"success": True}
    else:
        return {"success": False, "error": res.get("error")}


@router.post("/api/send-bulk-email", dependencies=[SEND_BULK])
async def send_bulk_email_endpoint(req: BulkEmailRequest, request: Request):
    """
    Triggers bulk outreach campaign, sending emails with a delay and streaming progress.
    """
    _require_smtp()

    async def bulk_event_generator():
        def make_event(status: str, message: str, **kwargs):
            return f"data: {json.dumps({'status': status, 'message': message, **kwargs})}\n\n"

        pool = await db_service.get_pool()
        leads = []
        
        # 1. Prepare leads list
        if req.leadIds is not None:
            try:
                async with pool.acquire() as conn:
                    rows = await conn.fetch("SELECT id, name, company, title, email FROM public.leads WHERE id = ANY($1::int[])", req.leadIds)
                    leads = [dict(r) for r in rows]
            except Exception as e:
                logger.error(f"Failed to fetch leads for bulk email: {e}")
                yield make_event("error", f"Failed to fetch leads: {str(e)}")
                return

            if not leads:
                yield make_event("error", "No leads found in database matching the provided IDs.")
                return
        elif req.leads is not None:
            leads = [l.model_dump(by_alias=True) for l in req.leads]
            if not leads:
                yield make_event("error", "No contacts provided for bulk email outreach.")
                return
        else:
            yield make_event("error", "Either leadIds or leads must be provided.")
            return

        total_leads = len(leads)
        sent_count = 0
        failed_count = 0
        
        yield make_event("start", f"Starting bulk email campaign for {total_leads} leads...", total=total_leads)

        for index, lead in enumerate(leads):
            to_email = lead.get("email")
            lead_id = lead.get("id")
            
            # Show progress: "Sending Email 1 of 50" (1-indexed)
            progress_msg = f"Sending Email {index + 1} of {total_leads}"
            yield make_event("progress", progress_msg, current=index + 1, total=total_leads, email=to_email)

            # Validation checks
            error_reason = None
            if not to_email or "@" not in to_email or "." not in to_email:
                error_reason = "Invalid or empty email address"
            
            if not error_reason:
                # Replace placeholders in subject and body
                formatted_subject = req.subject
                formatted_body = req.body
                
                # Simple placeholder replacement
                for placeholder, key in [("{name}", "name"), ("{company}", "company"), ("{title}", "title")]:
                    val = lead.get(key) or ""
                    formatted_subject = formatted_subject.replace(placeholder, val)
                    formatted_body = formatted_body.replace(placeholder, val)
                
                # Send email
                send_res = await send_email(to_email, formatted_subject, formatted_body)
                if send_res["success"]:
                    sent_count += 1
                    status = "sent"
                else:
                    failed_count += 1
                    status = "failed"
                    error_reason = send_res.get("error", "Unknown SMTP error")
            else:
                failed_count += 1
                status = "failed"

            # Update PostgreSQL database ONLY if operating on database lead IDs
            if req.leadIds is not None:
                try:
                    await db_service.update_lead_email_status(lead_id, status, error_reason)
                except Exception as e:
                    logger.error(f"Failed to update lead status in database: {e}")

            # Send details about current lead send result to frontend
            yield make_event(
                "status_update", 
                f"Email to {to_email} {status}" + (f": {error_reason}" if error_reason else ""),
                lead_id=lead_id, 
                email=to_email, 
                success=(status == "sent"), 
                error=error_reason
            )

            # Wait delay if not the last email
            if index < total_leads - 1:
                await asyncio.sleep(req.delay if req.delay is not None else 2.0)

        # Final summary: "50 Emails Processed | 48 Sent | 2 Failed"
        summary_msg = f"{total_leads} Emails Processed | {sent_count} Sent | {failed_count} Failed"
        _log_activity(
            request,
            "email.bulk_sent",
            entity_type="lead",
            metadata={
                "subject": req.subject,
                "total": total_leads,
                "sent": sent_count,
                "failed": failed_count,
                "leadIds": (req.leadIds or [])[:MAX_LOGGED_IDS],
            },
        )
        yield make_event(
            "completed", 
            summary_msg, 
            total=total_leads, 
            sent=sent_count, 
            failed=failed_count
        )

    return StreamingResponse(bulk_event_generator(), media_type="text/event-stream")


@router.get("/api/email-templates", dependencies=[SEND_EMAIL])
async def get_templates():
    """
    Get all saved email templates.
    """
    try:
        templates = await db_service.get_email_templates()
        return {"templates": templates}
    except Exception as e:
        logger.error(f"Failed to fetch templates: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch templates")


@router.post("/api/email-templates", dependencies=[MANAGE_TEMPLATES])
async def save_template(template: EmailTemplateSchema, request: Request):
    """
    Save or update an email template.
    """
    try:
        saved = await db_service.save_email_template(
            template_name=template.template_name,
            subject=template.subject,
            body=template.body,
            template_id=template.id
        )
        _log_activity(
            request,
            "email_template.updated" if template.id else "email_template.created",
            entity_type="email_template",
            entity_id=saved["id"],
            metadata={"name": template.template_name},
        )
        return {"success": True, "template": saved}
    except Exception as e:
        logger.error(f"Failed to save template: {e}")
        raise HTTPException(status_code=500, detail="Failed to save template")


@router.delete("/api/email-templates/{template_id}", dependencies=[MANAGE_TEMPLATES])
async def delete_template(template_id: int, request: Request):
    """
    Delete an email template.
    """
    try:
        await db_service.delete_email_template(template_id)
        _log_activity(request, "email_template.deleted", entity_type="email_template", entity_id=template_id)
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to delete template: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete template")

