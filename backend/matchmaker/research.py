"""
Company research: what does this business do, and what might it buy?

Sources, in order of trust:
  1. The company's own website (given, or from a business email domain).
     Outbound prospects with no website are looked up with Serper (the same
     search Lead Gen uses to discover companies) when SERPER_API_KEY is set.
  2. What the enquiry or upload said (industry, description, requirement).
  3. An AI summary of 1-2 (AI_PROVIDER), else a rule-based profile.

Nothing here is allowed to fail an analysis: a site that is down, a search
without results or an AI error each just lower the evidence quality.

Website URLs come from untrusted input (the public enquiry form, Excel
uploads), so pages are only fetched from public internet addresses
(ported unchanged from LeadMatch, see is_public_url).
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from backend.services.ai_client import AIUnavailable, complete_json
from backend.services.company_discovery import serper_search

from .utils import names_compatible, normalize_domain

logger = logging.getLogger(__name__)

MODEL_VERSION = "leadmatch-hybrid-v2"
MAX_REDIRECTS = 5
MAX_PAGE_BYTES = 2_000_000

# Sites that are never a company's own website.
DIRECTORY_HOSTS = (
    "linkedin.com", "facebook.com", "instagram.com", "twitter.com", "x.com", "youtube.com",
    "wikipedia.org", "yellowpages", "dubizzle.com", "zawya.com", "bloomberg.com", "crunchbase.com",
    "google.com", "maps.google", "tripadvisor", "glassdoor", "indeed.com", "naukri.com",
    "justdial.com", "indiamart.com", "tradeindia.com", "alibaba.com", "amazon.", "noon.com",
)


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip = False
        self.parts: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self._skip = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self._skip = False

    def handle_data(self, data):
        if self._skip:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if text:
            self.parts.append(text)


def _is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def is_public_url(url: str) -> bool:
    """True only for http(s) URLs on standard ports whose host resolves exclusively
    to public internet addresses: never localhost, private networks or cloud
    metadata endpoints."""
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if port not in (None, 80, 443):
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, port or (443 if parsed.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError):
        return False
    return bool(infos) and all(_is_public_ip(info[4][0]) for info in infos)


def _peer_is_public(resp: httpx.Response) -> bool:
    """Re-check the address actually connected to, guarding against DNS rebinding."""
    stream = resp.extensions.get("network_stream")
    if stream is None:
        return True
    addr = stream.get_extra_info("server_addr")
    if not addr:
        return True
    return _is_public_ip(str(addr[0]))


def fetch_page(url: str, timeout: float = 8.0, transport: httpx.BaseTransport | None = None) -> tuple[str, list[str]]:
    """(visible text, links) of a public web page, or ("", []) on any problem. Blocking."""
    headers = {"User-Agent": "LeadGenMatchmaker/1.0 (+internal-research)"}
    try:
        with httpx.Client(follow_redirects=False, timeout=timeout, headers=headers, trust_env=False, transport=transport) as client:
            for _ in range(MAX_REDIRECTS + 1):
                if not is_public_url(url):
                    return "", []
                with client.stream("GET", url) as resp:
                    if not _peer_is_public(resp):
                        return "", []
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            return "", []
                        url = urljoin(str(resp.url), location)
                        continue
                    if resp.status_code >= 400:
                        return "", []
                    body = b""
                    for chunk in resp.iter_bytes():
                        body += chunk
                        if len(body) >= MAX_PAGE_BYTES:
                            break
                    html = body.decode(resp.encoding or "utf-8", errors="replace")
                parser = _TextExtractor()
                parser.feed(html)
                return " ".join(parser.parts)[:12000], parser.links
            return "", []
    except Exception:  # noqa: BLE001 -- an unreachable site is just "no evidence"
        return "", []


def candidate_pages(website: str, links: list[str]) -> list[str]:
    base = website if website.startswith("http") else f"https://{website}"
    keywords = ("about", "product", "service", "industr", "facilit", "project", "capabilit")

    def _site(u: str) -> str:
        host = (urlparse(u).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host

    base_host = _site(base)
    found = [base]
    for href in links:
        if any(k in href.lower() for k in keywords):
            page = urljoin(base, href)
            if _site(page) == base_host:  # only the company's own site
                found.append(page)
        if len(found) >= 4:
            break
    seen: list[str] = []
    for u in found:
        if u not in seen:
            seen.append(u)
    return seen


def _read_site(website: str) -> tuple[str, list[str]]:
    texts: list[str] = []
    sources: list[str] = []
    home, links = fetch_page(website if "://" in website else f"https://{website}")
    if home:
        texts.append(home)
        sources.append(website)
    for page in candidate_pages(website, links)[1:]:
        body, _ = fetch_page(page)
        if body:
            texts.append(body)
            sources.append(page)
    return " ".join(texts)[:16000], sources


async def find_website(name: str, country: str | None) -> tuple[str | None, list[dict]]:
    """Search for the company's own site. Returns (website or None, search snippets)."""
    api_key = os.getenv("SERPER_API_KEY") or ""
    if not api_key or not name:
        return None, []
    results = await serper_search(f"{name} {country or ''}".strip(), api_key)
    for res in results[:8]:
        url = res.get("url") or ""
        host = (urlparse(url).hostname or "").lower()
        if not host or any(d in host for d in DIRECTORY_HOSTS):
            continue
        # Only accept a result whose title or domain plausibly names this company.
        domain_words = (normalize_domain(url) or "").split(".")[0].replace("-", " ")
        if names_compatible(name, res.get("title", "").split("|")[0].split("-")[0]) or names_compatible(name, domain_words):
            return f"https://{normalize_domain(url)}", results[:5]
    return None, results[:5]


def heuristic_profile(company, text: str) -> dict:
    lower = (text or "").lower()
    desc = (company.description or "").lower()
    industry = company.industry
    industry_map = [
        ("manufactur", "Manufacturing"), ("construct", "Construction"), ("warehouse", "Warehousing & Logistics"),
        ("logistics", "Warehousing & Logistics"), ("hospital", "Healthcare"), ("hotel", "Hospitality"),
        ("mining", "Mining"), ("steel", "Metals & Steel"), ("cement", "Cement"), ("automotive", "Automotive"),
        ("garage", "Automotive"), ("workshop", "Automotive"), ("pharma", "Pharmaceuticals"),
        ("food", "Food Processing"), ("textile", "Textiles"), ("power", "Power & Energy"), ("oil", "Oil & Gas"),
        ("chemical", "Chemicals"), ("retail", "Retail"), ("supermarket", "Retail"), ("real estate", "Real Estate"),
        ("facility", "Facility management"), ("ship", "Marine / Shipbuilding"), ("airport", "Aviation"),
    ]
    if not industry:
        for key, label in industry_map:
            if key in lower or key in (company.name or "").lower() or key in desc:
                industry = label
                break
    industry = industry or "General B2B"

    activities = [
        p for p in ("manufacturing", "fabrication", "assembly", "warehousing", "distribution", "construction",
                    "installation", "maintenance", "repair", "retail", "export", "import", "processing", "packaging")
        if p in lower or p in desc
    ]
    facilities = [p for p in ("factory", "plant", "warehouse", "workshop", "crane", "compressor", "lighting", "battery", "fleet") if p in lower or p in desc]
    summary_src = text[:400] if text else company.description or f"{company.name} operates in {company.country or 'an unspecified country'}."
    return {
        "industry": industry,
        "business_type": company.business_type or ("Manufacturer" if "manufactur" in lower else None),
        "products_manufactured": None,
        "services_offered": None,
        "business_activities": ", ".join(activities) or industry,
        "facilities": ", ".join(facilities) or None,
        "procurement_areas": None,
        "relevant_applications": industry,
        "summary": re.sub(r"\s+", " ", summary_src).strip(),
    }


PROFILE_FIELDS = (
    "industry", "business_type", "products_manufactured", "services_offered", "business_activities",
    "facilities", "procurement_areas", "relevant_applications", "summary",
)

PROFILE_SYSTEM = (
    "You analyse B2B companies for a sales team. From the facts and website text given, extract a structured "
    "business profile. Use only what the input supports; never invent facts. Use null when unknown. "
    "Return one JSON object only, no prose, no markdown."
)


async def ai_profile(company, text: str, enquiry: dict | None, snippets: list[dict]) -> dict | None:
    facts = {
        "company": {k: company.get(k) for k in ("name", "website", "country", "city", "industry", "sub_industry", "description")},
        "enquiry": enquiry or None,
        "search_results": [{"title": s.get("title"), "snippet": s.get("snippet"), "url": s.get("url")} for s in snippets[:5]],
        "website_text": text[:8000] or None,
    }
    prompt = (
        "Input:\n" + json.dumps(facts, ensure_ascii=False) + "\n\n"
        "Return JSON with exactly these keys (strings or null): "
        + ", ".join(PROFILE_FIELDS)
        + ". 'summary' is 2-3 plain sentences on what the company does. 'procurement_areas' lists what such a "
        "company typically buys to run its operations (consumables, spare parts, lighting, batteries, maintenance "
        "supplies...), as a comma-separated list. 'facilities' lists sites or equipment mentioned (workshop, "
        "warehouse, fleet, plant...)."
    )
    try:
        data = await complete_json(PROFILE_SYSTEM, prompt, max_tokens=4000)
    except AIUnavailable as exc:
        logger.info("AI company profile unavailable for %s: %s", company.id, exc)
        return None
    if not isinstance(data, dict):
        return None
    out = {}
    for key in PROFILE_FIELDS:
        val = data.get(key)
        if isinstance(val, list):
            val = ", ".join(str(v) for v in val if v)
        out[key] = str(val).strip()[:2000] if val not in (None, "", "null") else None
    return out if out.get("summary") or out.get("business_activities") else None


async def research(company, enquiry: dict | None = None, allow_search: bool = True) -> dict:
    """Profile of `company`: {profile fields..., sources, method, found_website}."""
    website = company.website or company.website_domain
    found_website = None
    snippets: list[dict] = []
    if not website and allow_search:
        try:
            found_website, snippets = await find_website(company.name, company.country)
        except Exception as exc:  # noqa: BLE001
            logger.info("Website search failed for %s: %s", company.id, type(exc).__name__)
        website = found_website

    text, sources = ("", [])
    if website:
        text, sources = await asyncio.to_thread(_read_site, website)

    profile = await ai_profile(company, text, enquiry, snippets)
    method = "ai" if profile else "rules"
    if not profile:
        snippet_text = " ".join(f"{s.get('title', '')} {s.get('snippet', '')}" for s in snippets)
        profile = heuristic_profile(company, f"{text} {snippet_text}".strip())
    if not sources and snippets:
        sources = [s["url"] for s in snippets if s.get("url")][:3]
    return {
        **profile,
        "sources": sources,
        "method": method,
        "found_website": found_website,
        "website_read": bool(text),
        "model_version": MODEL_VERSION,
    }
