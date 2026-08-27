import os
import json
import logging
import re
import asyncio
import httpx
from typing import List, Dict, Any, Callable, Optional, Union, Coroutine
from backend.services.company_discovery import serper_search

logger = logging.getLogger(__name__)

async def enrich_lead(
    lead: Dict[str, Any],
    api_key: str,
    serper_key: str
) -> Dict[str, Any]:
    """
    Enriches a single lead if it is missing crucial contact details.
    """
    email = (lead.get("email") or "").strip()
    phone = (lead.get("phone") or "").strip()
    name = (lead.get("name") or "").strip()
    linkedin = (lead.get("linkedIn") or lead.get("linkedin") or "").strip()

    # Determine if enrichment is required
    needs_enrichment = not email or not phone or not name or not linkedin
    if not needs_enrichment:
        return lead

    company_name = lead.get("company") or ""
    website = lead.get("website") or ""

    try:
        # Free-tier Serper compatible query (no OR/site: operators to avoid 400 Bad Request)
        query = f'"{company_name}" contact email phone procurement linkedin'

        logger.info(f"Enriching '{company_name}' using query: {query}")
        results = await serper_search(query, serper_key)

        if not results:
            logger.info(f"No search results found for '{company_name}' contact info.")
            return lead

        formatted_results = []
        for index, res in enumerate(results):
            formatted_results.append(f"[Result #{index + 1}]\nTitle: {res.get('title') or ''}\nURL: {res.get('url') or ''}\nSnippet: {res.get('snippet') or ''}")

        formatted_text = "\n\n".join(formatted_results)

        prompt = f"""Act as an expert B2B lead researcher.
We need to enrich contact details for the company: "{company_name}" (Website: "{website or 'N/A'}").
Below are search results from Google containing contact and decision maker info for this company.

SEARCH RESULTS:
{formatted_text}

Based ON THE SEARCH RESULTS ABOVE, extract or determine the missing contact information.
CRITICAL REQUIREMENTS:
1. Extract or infer high-quality contact details using the search results.
2. If the exact email address is not found in the search results, construct a highly plausible fallback business email using the verified website/domain name (e.g., if website is "muqarram.com", construct "info@muqarram.com" or "procurement@muqarram.com"). Never leave the email blank if a website domain is available.
3. For "phone", extract the phone number, prioritizing GCC numbers (+971 for UAE, +966 for KSA, +974 for Qatar, etc.). If not found in the search text, look for any general office number in the results. If none exists, leave it empty.
4. For "name" and "title", look for a procurement manager, purchasing manager, supply chain manager, general manager, owner, or other decision-makers. If no specific name is mentioned in the text, use a generic placeholder like "Procurement Dept" or "Purchasing Team" and job title "Procurement Team".
5. For "linkedIn", look for the LinkedIn profile URL of the contact person or the company LinkedIn page URL. If not explicitly found, construct a general company URL pattern (e.g., "linkedin.com/company/{company_name.lower().replace(' ', '')}").

Return the response STRICTLY as a JSON object matching the format below. Do not include any wrapper or comments.

JSON Output Format:
{{
  "name": "Contact Name or placeholder",
  "title": "Contact Job Title or placeholder",
  "email": "Contact Email or constructed fallback",
  "phone": "Contact Phone or empty string",
  "linkedIn": "LinkedIn URL or constructed fallback"
}}"""

        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise data-enrichment assistant. You only output valid JSON based strictly on the provided context."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            res_data = response.json()

        text = ""
        if "choices" in res_data and len(res_data["choices"]) > 0:
            text = res_data["choices"][0]["message"]["content"].strip()

        if not text:
            return lead

        # Strip markdown code block wraps
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        parsed = json.loads(text)

        # Merge fields only if original is missing
        enriched_lead = {
            **lead,
            "name": lead.get("name") if (lead.get("name") and lead.get("name").strip()) else (parsed.get("name") or ""),
            "title": lead.get("title") if (lead.get("title") and lead.get("title").strip()) else (parsed.get("title") or ""),
            "email": lead.get("email") if (lead.get("email") and lead.get("email").strip()) else (parsed.get("email") or ""),
            "phone": lead.get("phone") if (lead.get("phone") and lead.get("phone").strip()) else (parsed.get("phone") or ""),
            "linkedIn": lead.get("linkedIn") if (lead.get("linkedIn") and lead.get("linkedIn").strip()) else (parsed.get("linkedIn") or parsed.get("linkedin") or ""),
        }

        logger.info(f"Enriched lead for '{company_name}': {enriched_lead}")
        return enriched_lead

    except Exception as e:
        logger.error(f"Error enriching lead for '{company_name}': {e}")
        return lead


async def enrich_leads(
    leads: List[Dict[str, Any]],
    progress_callback: Optional[Callable[[str], Union[None, Coroutine[Any, Any, None]]]] = None
) -> List[Dict[str, Any]]:
    """
    Enriches a list of leads by searching for missing contact details in batches.
    """
    api_key = os.getenv("GROQ_API_KEY")
    serper_key = os.getenv("SERPER_API_KEY")

    if not api_key or not serper_key:
        logger.warning("GROQ_API_KEY or SERPER_API_KEY is not defined. Skipping enrichment.")
        return leads

    enriched_leads = []
    batch_size = 3

    for i in range(0, len(leads), batch_size):
        batch = leads[i : i + batch_size]
        progress_msg = f"Enriching contact info for companies {i + 1} to {min(i + batch_size, len(leads))} of {len(leads)}..."
        logger.info(progress_msg)
        
        # Trigger progress callback if supplied
        if progress_callback:
            if asyncio.iscoroutinefunction(progress_callback):
                await progress_callback(progress_msg)
            else:
                progress_callback(progress_msg)

        # Process the batch concurrently
        enrichment_tasks = [enrich_lead(lead, api_key, serper_key) for lead in batch]
        enriched_batch = await asyncio.gather(*enrichment_tasks)
        enriched_leads.extend(enriched_batch)

    return enriched_leads
