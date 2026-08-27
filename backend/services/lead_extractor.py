import os
import json
import logging
import httpx
from urllib.parse import urlparse
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def get_domain(url: str) -> str:
    """
    Extracts the unique domain name from a URL to identify different companies.
    """
    if not url:
        return ""
    url = url.strip().lower()
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc or ""
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""

async def extract_leads(search_results: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    Sends search results to Claude or Groq to extract B2B leads based STRICTLY on the search data.
    """
    if not search_results:
        return []

    # 1. Deduplicate by domain and truncate snippets to prevent payload limits
    seen_domains = set()
    unique_results = []
    
    for res in search_results:
        url = res.get("url") or ""
        domain = get_domain(url)
        if not domain:
            continue
        if domain not in seen_domains:
            seen_domains.add(domain)
            snippet = res.get("snippet") or ""
            if len(snippet) > 400:
                snippet = snippet[:400] + "..."
            unique_results.append({
                "title": res.get("title") or "",
                "url": url,
                "snippet": snippet
            })

    # Limit to top 25 unique companies
    unique_results = unique_results[:25]

    # Format search results for the prompt
    formatted_results = []
    for index, res in enumerate(unique_results):
        formatted_results.append(f"""[Result #{index + 1}]
Title: {res['title']}
URL: {res['url']}
Snippet: {res['snippet']}""")

    formatted_text = "\n\n".join(formatted_results)

    prompt = f"""Act as an expert B2B lead generation specialist and data miner.
Extract real business contacts and companies from the following search results.

---
SEARCH RESULTS:
{formatted_text}
---

CRITICAL REQUIREMENTS:
1. Extract business listings, company details, and contacts present in the search results above.
2. If the exact email address is not found in the search results but a website domain is present, construct a highly plausible fallback business email (e.g. info@domain.com or procurement@domain.com where domain.com is the company's verified domain). Never leave the email blank if a website domain is available.
3. If no specific contact person name is found in the text, use a generic placeholder like "Procurement Dept" or "Purchasing Team" and job title "Procurement Team" (or "Procurement Manager").
4. For "phone", extract the phone number or general office phone number from the text if available, otherwise set it to an empty string "".
5. The "website" field MUST be the actual domain name of the company derived from the search result URL or snippet (e.g. "alghanim.com").
6. Based on the business details, classify each lead into the following classifications:
   - segment: MUST be one of: "Distributor", "Wholesaler", "Retail", "Contractor", "Industrial", "Manufacturing", "Facility Management", "Government", "Healthcare", "Hospitality", "Enterprise", "End User", "Other".
   - priority: MUST be one of: "High", "Medium", "Low". (High if the company is highly relevant and has contacts, Low if fit is general).
   - channel: MUST be one of: "Distributor", "Direct Customer", "Contractor", "Retail", "Project", "Service", "Workshop", "Fleet".
7. Return the response STRICTLY as a JSON object containing a "leads" array.

You MUST return the output strictly as a JSON object matching the format below.
Do not include any wrapper (like markdown code blocks ```json), comments, or introductory text. Return ONLY the raw JSON string.

JSON Output Format:
{{
  "leads": [
    {{
      "company": "Company Name",
      "name": "Decision Maker Name or placeholder (e.g. Procurement Dept)",
      "title": "Job Title or placeholder (e.g. Procurement Team)",
      "email": "Email Address or constructed fallback (e.g. info@company.com)",
      "phone": "Phone Number or empty string",
      "website": "Company Website URL or Domain (must be present)",
      "linkedIn": "LinkedIn Profile URL or Company Page URL (or empty string if not found)",
      "location": "City/Region, Country (e.g. Dubai, UAE)",
      "segment": "Segment Category",
      "priority": "Priority Level",
      "channel": "Channel Category"
    }}
  ]
}}"""

    provider = os.getenv("AI_PROVIDER", "claude").lower()
    text = ""

    try:
        if provider == "groq":
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY is not defined in the environment.")
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
                        "content": "You are a precise data-extraction assistant. You only output valid JSON based strictly on the provided context."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.2,
                "max_tokens": 4096
            }

            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                res_data = response.json()
                if "choices" in res_data and len(res_data["choices"]) > 0:
                    text = res_data["choices"][0]["message"]["content"].strip()
        else:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY is not defined in the environment.")
            
            from anthropic import AsyncAnthropic
            client = AsyncAnthropic(api_key=api_key)
            
            response = await client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=4000,
                system="You are a precise data-extraction assistant. You only output valid JSON based strictly on the provided context.",
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )
            if response.content and len(response.content) > 0:
                text = response.content[0].text.strip()

        if not text:
            return []

        # Strip markdown wrappers if present
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        parsed = json.loads(text)
        if "leads" in parsed and isinstance(parsed["leads"], list):
            return parsed["leads"]
            
        return []
    except Exception as e:
        logger.error(f"Error extracting leads using {provider.upper()} service: {e}")
        raise e
