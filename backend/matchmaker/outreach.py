"""
Customer-facing WhatsApp and email drafts (ported from LeadMatch, extended to
cover several products and the company analysis).

Three situations, written differently on purpose:

* requested    - inbound: the customer asked for these products. Thank them,
                 repeat exactly what they asked for and ask the few details
                 needed for an accurate quotation. Chosen suggestions are
                 offered as optional additions to the same quotation.
* cross_sell   - inbound, but only suggestions were chosen: tie them to the
                 original request.
* introduction - outbound / no enquiry: a short, honest introduction tied to
                 what the company does, and an offer of a price list. Never
                 claims the company asked for anything.

Drafts never contain internal wording (scores, "evidence", "Matchmaker") and
are always reviewed and sent by a person. personalize() can rewrite a draft
with AI, constrained to the same facts; the rule-based draft is the fallback.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass

from backend.services.ai_client import AIUnavailable, complete_json

from .utils import digits_only

MAX_ITEMS = 6


def sender() -> dict:
    """How the business signs drafts. Set with MATCHMAKER_SENDER_* (defaults: V.V. & Sons)."""
    env = os.getenv
    return {
        "company": env("MATCHMAKER_SENDER_COMPANY", "V.V. & Sons LLC"),
        "short": env("MATCHMAKER_SENDER_SHORT_NAME", "V.V. & Sons"),
        "intro": env(
            "MATCHMAKER_SENDER_INTRO",
            "supplying automotive, battery, lighting and industrial maintenance products across the UAE since 1958",
        ),
        "phone": env("MATCHMAKER_SENDER_PHONE", "+971 52 819 4988"),
        "email": env("MATCHMAKER_SENDER_EMAIL", "cpd@vvsons.ae"),
        "website": env("MATCHMAKER_SENDER_WEBSITE", "vvsgrocer.com"),
        "region": env("MATCHMAKER_SENDER_REGION", "the UAE"),
        "city": env("MATCHMAKER_SENDER_CITY", "Dubai"),
    }


def default_country_code() -> str:
    return digits_only(os.getenv("MATCHMAKER_DEFAULT_COUNTRY_CODE", "971")) or "971"


@dataclass
class Draft:
    situation: str  # "requested" | "cross_sell" | "introduction"
    whatsapp: str
    subject: str
    email: str
    personalized: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def international_number(raw: str | None, country_code: str | None = None) -> str:
    """Digits for wa.me. Local numbers get the default country code:
    050 123 4567 -> 971501234567, 50 123 4567 -> 971501234567, 00971... -> 971..."""
    cc = country_code or default_country_code()
    digits = digits_only(raw)
    if not digits:
        return ""
    if (raw or "").strip().startswith("+"):
        return digits
    if digits.startswith("00"):
        return digits[2:]
    if digits.startswith(cc):
        return digits
    if digits.startswith("0"):
        return cc + digits[1:]
    if len(digits) == 9 and digits.startswith("5"):  # UAE mobile without the leading 0
        return cc + digits
    return digits


def first_name(full_name: str | None) -> str:
    name = (full_name or "").strip()
    if not name or name.lower() in {"website visitor", "customer"}:
        return ""
    return name.split()[0]


def requested_items(lead) -> list[str]:
    """Product names the customer asked for, from the enquiry text (website format) or fields."""
    if not lead:
        return []
    items: list[str] = []
    for line in (lead.requirement_description or "").splitlines():
        line = line.strip()
        if line.startswith("Product:"):
            text = re.sub(r"\(SKU[^)]*\)", "", line[len("Product:"):])
            items += [p.strip() for p in text.split("|")]
        elif line.startswith("Items:"):
            items += [p.strip() for p in re.split(r"[\n;]", line[len("Items:"):])]
        elif line.startswith("Selected products:"):
            items += [p.strip() for p in re.split(r"[,;]", line[len("Selected products:"):])]
    if not items and lead.interested_product:
        items = [lead.interested_product]
    seen, out = set(), []
    for item in items:
        if item and item.lower() not in seen:
            seen.add(item.lower())
            out.append(item)
    return out[:MAX_ITEMS]


def line_brands(product) -> str:
    """Brands stocked for a catalogue line, from its description ("… from OSRAM, GP Batteries. Examples …")."""
    m = re.search(r"\bfrom (.+?)\. Examples", (product.description if product else "") or "")
    return m.group(1).strip() if m else ""


def line_uses(product, limit: int = 3) -> str:
    parts = [p.strip().lower() for p in ((product.applications if product else "") or "").split(",") if p.strip()]
    return ", ".join(parts[:limit])


def _line_label(product) -> str:
    brands = line_brands(product)
    return f"{product.name} ({brands})" if brands else product.name


def _bullets(items: list[str], prefix: str = "- ") -> str:
    return "\n".join(f"{prefix}{i}" for i in items)


def _is_team(agent: str, s: dict) -> bool:
    low = agent.lower()
    return s["short"].lower() in low or "team" in low.split()


def _who(agent: str, where: str, s: dict) -> str:
    if _is_team(agent, s):
        return agent if agent.lower().startswith("the ") else f"the {agent}"
    return f"{agent} from {where}"


def _signature(agent: str, s: dict) -> str:
    contact = " | ".join(x for x in [s["phone"], s["email"], s["website"]] if x)
    company = "" if _is_team(agent, s) else f"\n{s['company']}"
    return f"Kind regards,\n{agent}{company}\n{contact}"


def _what_they_do(company, research) -> str:
    """A short, factual clause about the buyer's business, or ""."""
    industry = (company.industry or (research.industry if research else None) or "").strip()
    if industry.lower() in {"", "general b2b"}:
        return ""
    return industry.lower()


def build_draft(company, lead, products: list, suggestions: list, contact_name: str | None, agent_name: str, research=None) -> Draft:
    """
    products     catalogue lines the customer asked for (primary matches), may be empty
    suggestions  additional lines sales chose to offer
    """
    s = sender()
    agent = (agent_name or "").strip() or f"The {s['short']} team"
    brand = s["short"]
    ref = (lead.external_reference if lead else None) or ""
    ref_text = f" ({ref})" if ref else ""
    hello = f"Hello {first_name(contact_name)}" if first_name(contact_name) else "Hello"
    dear = f"Dear {contact_name.strip()}" if first_name(contact_name) else f"Dear {company.name} team"
    extra = [_line_label(p) for p in suggestions[:3]]
    is_inbound = bool(lead and lead.lead_type == "inbound")

    if is_inbound:
        items = requested_items(lead) or [_line_label(p) for p in products] or [
            x for x in [lead.interested_division] if x
        ]
        asked = lead.interested_product or (items[0] if items else None) or lead.interested_division or "your enquiry"
        if items:
            qty = f"Quantity: {lead.quantity}" if lead.quantity else ""
            wa_extra = (
                f"\n\nCustomers who order {asked} often also need:\n{_bullets(extra, '• ')}\nShall we include these in the same quotation?"
                if extra else ""
            )
            whatsapp = (
                f"{hello}, this is {_who(agent, brand, s)}. Thank you for your enquiry{ref_text} for:\n"
                f"{_bullets(items, '• ')}\n"
                + (f"{qty}\n" if qty else "")
                + f"\nWe will share pricing and availability shortly. Could you please confirm the exact quantity and your delivery location in {s['region']}?"
                + wa_extra
            )
            subject = f"Your {brand} enquiry{ref_text} – {asked}"
            email_extra = (
                f"Customers who order {asked} often also need:\n\n{_bullets(extra)}\n\n"
                "If useful, we can add these to the same quotation so everything arrives in one delivery.\n\n"
                if extra else ""
            )
            email = (
                f"{dear},\n\n"
                f"Thank you for your enquiry{(' (reference ' + ref + ')') if ref else ''}. You asked about:\n\n"
                f"{_bullets(items)}\n"
                + (f"\n{qty}\n" if qty else "")
                + "\nWe are checking availability and will send you a quotation with pricing and delivery details shortly. "
                "So that the quotation is accurate, could you please confirm:\n\n"
                "- the exact quantity you need\n"
                "- your delivery location\n"
                "- whether the invoice should be in your company's name (with TRN)\n\n"
                + email_extra
                + "If you would rather talk it through, just reply to this email or message us on WhatsApp.\n\n"
                f"{_signature(agent, s)}"
            )
            return Draft("requested", whatsapp, subject, email)

        # An enquiry with no product named: offer the chosen lines.
        lines = extra or ["our product range"]
        whatsapp = (
            f"{hello}, this is {_who(agent, brand, s)}, following up on your enquiry{ref_text}. "
            f"Based on what you told us, these could be useful:\n{_bullets(lines, '• ')}\n"
            "Which of these would you like a quotation for, and in what quantity?"
        )
        subject = f"Following up on your {brand} enquiry{ref_text}"
        email = (
            f"{dear},\n\nThank you for your enquiry{ref_text}. Based on what you told us, these could be useful:\n\n"
            f"{_bullets(lines)}\n\nReply with the items and quantities you need and we will send a quotation "
            f"with pricing and delivery details.\n\n{_signature(agent, s)}"
        )
        return Draft("cross_sell", whatsapp, subject, email)

    # Outbound prospect: an introduction, no claims they asked for anything.
    lines = [_line_label(p) for p in (suggestions or products)[:3]] or ["our product range"]
    business = _what_they_do(company, research)
    audience = f"{business} businesses" if business else "businesses"
    uses = line_uses((suggestions or products)[0]) if (suggestions or products) else ""
    tie_in = f"As a {business} business, {company.name} may find these useful" if business else f"These may be useful for {company.name}"
    whatsapp = (
        f"{hello}, this is {_who(agent, s['company'], s)} in {s['city']}. "
        f"We supply {', '.join(lines)} to {audience} across {s['region']}. "
        f"Would it be useful if we sent you our price list for {company.name}?"
    )
    subject = f"{(suggestions or products)[0].name if (suggestions or products) else 'Product supply'} for {company.name} – {brand}"
    intro = (
        f"We are {s['company']}, {s['intro']}.\n\n"
        if _is_team(agent, s)
        else f"I am {agent} from {s['company']}, {s['intro']}.\n\n"
    )
    email = (
        f"{dear},\n\n"
        + intro
        + f"{tie_in}:\n\n{_bullets(lines)}\n\n"
        + (f"They are commonly used for {uses}. " if uses else "")
        + f"We supply {audience} across {s['region']} with fast local delivery.\n\n"
        f"Would you be open to receiving our price list, or a short call to see whether these could help {company.name}?\n\n"
        f"{_signature(agent, s)}"
    )
    return Draft("introduction", whatsapp, subject, email)


PERSONALIZE_SYSTEM = (
    "You write short, warm, professional B2B sales messages for a distributor's sales team. You rewrite a draft "
    "WhatsApp message and email so they read naturally and are tailored to the customer, using ONLY the facts "
    "provided. Never invent prices, stock, delivery times, discounts, certifications, or anything the customer "
    "said. Keep every requested product and the enquiry reference exactly as given. Do not mention scores, "
    "analysis, research, AI or internal systems. Return one JSON object only."
)


async def personalize(draft: Draft, facts: dict) -> Draft:
    """AI rewrite of a draft using the same facts. Raises AIUnavailable (caller keeps the rule-based draft)."""
    prompt = (
        "Facts (the only things you may rely on):\n"
        + json.dumps(facts, ensure_ascii=False, default=str)
        + "\n\nDraft to improve:\n"
        + json.dumps({"whatsapp": draft.whatsapp, "subject": draft.subject, "email": draft.email}, ensure_ascii=False)
        + "\n\nReturn JSON {\"whatsapp\": str, \"subject\": str, \"email\": str}. WhatsApp: under 90 words, no "
        "subject line. Email: under 220 words, keep the signature block exactly as in the draft. Same language as "
        "the draft."
    )
    data = await complete_json(PERSONALIZE_SYSTEM, prompt, max_tokens=4000)
    if not isinstance(data, dict) or not all(isinstance(data.get(k), str) and data[k].strip() for k in ("whatsapp", "subject", "email")):
        raise AIUnavailable("The AI draft was incomplete")
    ref = facts.get("enquiry_reference")
    if ref and (ref not in data["whatsapp"] or ref not in data["email"]):
        raise AIUnavailable("The AI draft dropped the enquiry reference")
    return Draft(draft.situation, data["whatsapp"].strip(), data["subject"].strip()[:200], data["email"].strip(), True)
