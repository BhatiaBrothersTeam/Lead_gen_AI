import logging
from typing import List, Dict, Any, Optional
from datetime import datetime as dt_class, date as date_class
from backend.database.connection import get_pool

logger = logging.getLogger(__name__)

def serialize_db_lead(lead_dict: Dict[str, Any]) -> Dict[str, Any]:
    if not lead_dict:
        return lead_dict
    res = {}
    for k, v in lead_dict.items():
        if isinstance(v, (dt_class, date_class)):
            res[k] = v.isoformat()
        else:
            res[k] = v
    return res

async def initialize_tables():
    """
    Initializes database tables public.leads and public.product_services.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 1. Initialize leads table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS public.leads (
                id SERIAL PRIMARY KEY,
                name text,
                title text,
                company text,
                email text,
                phone text,
                website text,
                location text,
                linkedin text,
                segment text,
                priority text,
                channel text,
                division text NOT NULL DEFAULT 'Not Specified',
                created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
                verified boolean DEFAULT true
            )
        """)

        # Alter table to add email tracking columns if they don't exist
        cols = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='leads'")
        col_names = {r["column_name"] for r in cols}
        
        if "division" not in col_names:
            await conn.execute("ALTER TABLE public.leads ADD COLUMN division text NOT NULL DEFAULT 'Not Specified'")
        if "email_sent" not in col_names:
            await conn.execute("ALTER TABLE public.leads ADD COLUMN email_sent boolean DEFAULT false")
        if "email_sent_date" not in col_names:
            await conn.execute("ALTER TABLE public.leads ADD COLUMN email_sent_date timestamp without time zone")
        if "email_status" not in col_names:
            await conn.execute("ALTER TABLE public.leads ADD COLUMN email_status varchar(50)")
        if "email_error" not in col_names:
            await conn.execute("ALTER TABLE public.leads ADD COLUMN email_error text")

        # 2. Initialize product_services table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS public.product_services (
                id SERIAL PRIMARY KEY,
                category_type text,
                product_service_type text,
                product_service_name text
            )
        """)

        # 3. Initialize email_templates table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS public.email_templates (
                id SERIAL PRIMARY KEY,
                template_name text NOT NULL,
                subject text NOT NULL,
                body text NOT NULL,
                created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Insert mock data if empty
        val = await conn.fetchval("SELECT 1 FROM public.product_services LIMIT 1")
        if not val:
            await conn.execute("""
                INSERT INTO public.product_services (category_type, product_service_type, product_service_name) VALUES
                ('PACKAGE', 'Software', 'Basic Package'),
                ('PACKAGE', 'Software', 'Pro Package'),
                ('SERVICE', 'Consulting', 'IT Strategy'),
                ('SERVICE', 'Consulting', 'Security Audit'),
                ('SERVICE', 'Maintenance', 'Server Maintenance')
            """)


async def get_product_service_types(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieves categories from public.product_service_type.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        if category:
            query = "SELECT id, type FROM public.product_service_type WHERE UPPER(category_type) = UPPER($1) ORDER BY id ASC"
            rows = await conn.fetch(query, category)
        else:
            query = "SELECT id, type FROM public.product_service_type ORDER BY id ASC"
            rows = await conn.fetch(query)
            
        return [{"id": row["id"], "type": row["type"]} for row in rows]


async def get_product_service_names(type_id: int, category: str) -> List[str]:
    """
    Retrieves distinct product/service names from public.product_service_name.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT name FROM public.product_service_name WHERE product_service_type_id = $1 AND UPPER(category_type) = UPPER($2)",
            type_id, category
        )
        return [row["name"] for row in rows]


async def filter_existing_leads(leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Checks list of incoming leads and filters out ones that match existing records in public.leads.
    """
    if not leads:
        return []

    incoming_emails = [l.get("email") for l in leads if l.get("email")]
    incoming_phones = [l.get("phone") for l in leads if l.get("phone")]
    # support both linkedIn and linkedin properties
    incoming_linkedin = [l.get("linkedIn") or l.get("linkedin") for l in leads if (l.get("linkedIn") or l.get("linkedin"))]

    existing_emails = set()
    existing_phones = set()
    existing_linkedin = set()

    if incoming_emails or incoming_phones or incoming_linkedin:
        pool = await get_pool()
        async with pool.acquire() as conn:
            query = """
                SELECT email, phone, linkedin, division FROM public.leads
                WHERE email = ANY($1::text[]) 
                   OR phone = ANY($2::text[]) 
                   OR linkedin = ANY($3::text[])
            """
            rows = await conn.fetch(query, incoming_emails, incoming_phones, incoming_linkedin)
            for r in rows:
                division = (r["division"] or "").strip().lower() or "not specified"
                if r["email"]:
                    existing_emails.add((r["email"].lower(), division))
                if r["phone"]:
                    existing_phones.add((r["phone"].strip(), division))
                if r["linkedin"]:
                    existing_linkedin.add((r["linkedin"].lower(), division))

    unique_leads = []
    for l in leads:
        email = (l.get("email") or "").strip().lower()
        phone = (l.get("phone") or "").strip()
        li = (l.get("linkedIn") or l.get("linkedin") or "").strip().lower()
        division = (l.get("division") or "").strip().lower() or "not specified"

        has_email = email and (email, division) in existing_emails
        has_phone = phone and (phone, division) in existing_phones
        has_linkedin = li and (li, division) in existing_linkedin

        if not (has_email or has_phone or has_linkedin):
            unique_leads.append(l)

    return unique_leads


async def save_leads_directly(leads: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Directly appends leads to the public.leads table without deduplication.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Ensure table is initialized
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS public.leads (
                id SERIAL PRIMARY KEY,
                name text,
                title text,
                company text,
                email text,
                phone text,
                website text,
                location text,
                linkedin text,
                segment text,
                priority text,
                channel text,
                division text NOT NULL DEFAULT 'Not Specified',
                created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
                verified boolean DEFAULT true
            )
        """)

        query = """
            INSERT INTO public.leads(name, title, company, email, phone, website, location, linkedin, segment, priority, channel, division, verified)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, true)
            RETURNING *
        """
        processed_leads = []
        for lead in leads:
            row = await conn.fetchrow(
                query,
                lead.get("name"),
                lead.get("title"),
                lead.get("company"),
                lead.get("email"),
                lead.get("phone"),
                lead.get("website"),
                lead.get("location"),
                lead.get("linkedIn") or lead.get("linkedin"),
                lead.get("segment"),
                lead.get("priority"),
                lead.get("channel"),
                (lead.get("division") or "").strip() or "Not Specified"
            )
            processed_leads.append(serialize_db_lead(dict(row)))
            
    return {"success": True, "count": len(leads), "leads": processed_leads}



async def save_or_update_leads(leads: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Saves a batch of leads to PostgreSQL, applying deduplication and updating missing fields.
    """
    new_leads_added = 0
    existing_leads_updated = 0
    duplicates_skipped = 0
    processed_leads = []

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Ensure table exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS public.leads (
                id SERIAL PRIMARY KEY,
                name text,
                title text,
                company text,
                email text,
                phone text,
                website text,
                location text,
                linkedin text,
                segment text,
                priority text,
                channel text,
                division text NOT NULL DEFAULT 'Not Specified',
                created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
                verified boolean DEFAULT true
            )
        """)

        for lead in leads:
            match_conditions = []
            params = []

            company = lead.get("company")
            email = lead.get("email")
            website = lead.get("website")
            division = (lead.get("division") or "").strip() or "Not Specified"

            if company and company.strip() != "":
                params.append(company.strip())
                match_conditions.append(f"(company IS NOT NULL AND LOWER(company) = LOWER(${len(params)}))")
            if email and email.strip() != "":
                params.append(email.strip())
                match_conditions.append(f"(email IS NOT NULL AND LOWER(email) = LOWER(${len(params)}))")
            if website and website.strip() != "":
                params.append(website.strip())
                match_conditions.append(f"(website IS NOT NULL AND LOWER(website) = LOWER(${len(params)}))")

            existing_record = None
            if match_conditions:
                params.append(division)
                check_query = f"SELECT * FROM public.leads WHERE ({' OR '.join(match_conditions)}) AND LOWER(division) = LOWER(${len(params)}) LIMIT 1"
                try:
                    existing_record = await conn.fetchrow(check_query, *params)
                except Exception as err:
                    logger.error(f"Error querying duplicate leads in database: {err}")

            if existing_record:
                fields_to_update = []
                schema_fields = [
                    {"key": "name", "col": "name"},
                    {"key": "title", "col": "title"},
                    {"key": "company", "col": "company"},
                    {"key": "email", "col": "email"},
                    {"key": "phone", "col": "phone"},
                    {"key": "website", "col": "website"},
                    {"key": "location", "col": "location"},
                    {"key": "linkedIn", "col": "linkedin"},
                    {"key": "linkedin", "col": "linkedin"},
                    {"key": "segment", "col": "segment"},
                    {"key": "priority", "col": "priority"},
                    {"key": "channel", "col": "channel"},
                ]

                # Map asyncpg Record to dict
                db_record_dict = dict(existing_record)

                for field in schema_fields:
                    db_val = db_record_dict.get(field["col"])
                    input_val = lead.get(field["key"]) or lead.get(field["col"])

                    # Sync logic
                    if (
                        (db_val is None or str(db_val).strip() == "") and
                        input_val and
                        str(input_val).strip() != ""
                    ):
                        fields_to_update.append({"column": field["col"], "value": str(input_val).strip()})

                # Avoid duplicate mapping updates for 'linkedin' column if both key names exist
                unique_updates = []
                seen_cols = set()
                for upd in fields_to_update:
                    if upd["column"] not in seen_cols:
                        seen_cols.add(upd["column"])
                        unique_updates.append(upd)

                if unique_updates:
                    set_clauses = [f"{upd['column']} = ${idx + 2}" for idx, upd in enumerate(unique_updates)]
                    update_params = [db_record_dict["id"]] + [upd["value"] for upd in unique_updates]
                    update_query = f"UPDATE public.leads SET {', '.join(set_clauses)} WHERE id = $1 RETURNING *"
                    
                    try:
                        updated_row = await conn.fetchrow(update_query, *update_params)
                        existing_leads_updated += 1
                        processed_leads.append(serialize_db_lead(dict(updated_row)))
                    except Exception as update_err:
                        logger.error(f"Error partially updating lead ID {db_record_dict['id']}: {update_err}")
                        processed_leads.append(serialize_db_lead(db_record_dict))
                else:
                    duplicates_skipped += 1
                    processed_leads.append(serialize_db_lead(db_record_dict))
            else:
                # No duplicate, insert new
                insert_query = """
                    INSERT INTO public.leads (name, title, company, email, phone, website, location, linkedin, segment, priority, channel, division, verified)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, true)
                    RETURNING *
                """
                try:
                    inserted_row = await conn.fetchrow(
                        insert_query,
                        lead.get("name") or "",
                        lead.get("title") or "",
                        lead.get("company") or "",
                        lead.get("email") or "",
                        lead.get("phone") or "",
                        lead.get("website") or "",
                        lead.get("location") or "",
                        lead.get("linkedIn") or lead.get("linkedin") or "",
                        lead.get("segment") or "",
                        lead.get("priority") or "",
                        lead.get("channel") or "",
                        division,
                    )
                    new_leads_added += 1
                    processed_leads.append(serialize_db_lead(dict(inserted_row)))
                except Exception as insert_err:
                    logger.error(f"Error inserting new lead: {insert_err}")

    return {
        "totalFound": len(leads),
        "newLeadsAdded": new_leads_added,
        "existingLeadsUpdated": existing_leads_updated,
        "duplicatesSkipped": duplicates_skipped,
        "leads": processed_leads,
    }


async def update_lead_email_status(lead_id: int, status: str, error_msg: Optional[str] = None) -> bool:
    """
    Updates the email sending status and timestamp for a specific lead.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        sent = (status.lower() == "sent")
        query = """
            UPDATE public.leads 
            SET email_sent = $2, 
                email_sent_date = CURRENT_TIMESTAMP, 
                email_status = $3, 
                email_error = $4 
            WHERE id = $1
        """
        await conn.execute(query, lead_id, sent, status, error_msg)
        return True


async def get_email_templates() -> List[Dict[str, Any]]:
    """
    Retrieves all saved email templates from public.email_templates.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, template_name, subject, body, created_at FROM public.email_templates ORDER BY id ASC")
        return [
            {
                "id": r["id"],
                "template_name": r["template_name"],
                "subject": r["subject"],
                "body": r["body"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None
            }
            for r in rows
        ]


async def save_email_template(template_name: str, subject: str, body: str, template_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Saves a new template or updates an existing one.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        if template_id:
            row = await conn.fetchrow("""
                UPDATE public.email_templates 
                SET template_name = $2, subject = $3, body = $4 
                WHERE id = $1 
                RETURNING id, template_name, subject, body, created_at
            """, template_id, template_name, subject, body)
        else:
            row = await conn.fetchrow("""
                INSERT INTO public.email_templates (template_name, subject, body) 
                VALUES ($1, $2, $3) 
                RETURNING id, template_name, subject, body, created_at
            """, template_name, subject, body)
        
        return {
            "id": row["id"],
            "template_name": row["template_name"],
            "subject": row["subject"],
            "body": row["body"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None
        }


async def delete_email_template(template_id: int) -> bool:
    """
    Deletes an email template by ID.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM public.email_templates WHERE id = $1", template_id)
        return True

