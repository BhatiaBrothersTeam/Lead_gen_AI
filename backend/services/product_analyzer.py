import os
import json
import logging
import httpx
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

async def analyze_product(
    division: str,
    product_name: str,
    brand: str = "Not Specified",
    description: str = "Not Specified"
) -> Dict[str, Any]:
    """
    Analyzes the product using Groq to extract keywords, industries, competitors, and buyer types.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not defined in the environment.")

    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

    prompt = f"""Act as an expert B2B product researcher and market analyst specializing in the Middle East / GCC market.
Analyze the following product/service details to help us find high-quality sales leads:

- Division: {division or 'Not Specified'}
- Product Name: {product_name}
- Brand: {brand or 'Not Specified'}
- Description: {description or 'Not Specified'}

Based on this information, determine the following:
1. Industry (e.g. Automotive Chemicals, Industrial Equipment)
2. Sub Industry
3. Product Category
4. Buyer Types (e.g. workshops, fleet companies, auto parts distributors)
5. Competitor Brands (e.g. STP, Liqui Moly)
6. Search Keywords (specific search terms to find suppliers, distributors, wholesalers, or buyers of this product type in UAE/GCC, e.g. "fuel additive distributor UAE", "octane booster supplier Dubai")
7. Alternative Search Terms (e.g. "automotive chemical wholesaler GCC")

You MUST return the output strictly as a JSON object matching the format below.
Do not include any wrapper (like markdown code blocks ```json), comments, or introductory text. Return ONLY the raw JSON string.

JSON format:
{{
  "industry": "Industry name",
  "subIndustry": "Sub Industry name",
  "productCategory": "Product Category name",
  "buyerTypes": ["Buyer Type 1", "Buyer Type 2"],
  "competitorBrands": ["Brand 1", "Brand 2"],
  "competitors": ["Brand 1", "Brand 2"],
  "searchKeywords": ["Keyword 1", "Keyword 2"],
  "keywords": ["Keyword 1", "Keyword 2"],
  "alternativeSearchTerms": ["Alternative Term 1", "Alternative Term 2"]
}}"""

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise B2B market intelligence data extraction assistant. You only output valid raw JSON."
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
            raise ValueError("Empty response from Groq API")

        # Clean markdown code block wraps if present
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        parsed = json.loads(text)
        return parsed
    except Exception as e:
        logger.error(f"Error in product analyzer service: {e}")
        raise e

