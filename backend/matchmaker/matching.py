"""
Product matching: score every active catalogue line against what we know about
the buyer (company profile + research + the enquiry), ported from LeadMatch's
hybrid engine.

* primary_requirement - the buyer asked for this line (inbound only)
* cross_sell          - an inbound buyer's additional opportunity
* potential_opportunity - an outbound prospect's likely fit (not yet verified)

Pure functions over plain rows: no database access here.
"""
from __future__ import annotations

import re

from .utils import tokenize

MAX_RECOMMENDATIONS = 12
MAX_PER_DIVISION = 4


def _buyer_text(company, research, lead) -> str:
    return " ".join(
        filter(
            None,
            [
                company.name, company.industry, company.sub_industry, company.description, company.business_type,
                research.summary if research else None,
                research.business_activities if research else None,
                research.products_manufactured if research else None,
                research.services_offered if research else None,
                research.procurement_areas if research else None,
                research.facilities if research else None,
                research.relevant_applications if research else None,
                lead.requirement_description if lead else None,
                lead.application if lead else None,
                lead.interested_product if lead else None,
                lead.interested_division if lead else None,
            ],
        )
    ).lower()


def score_product(company, research, product, lead, exact_line_requested: bool = False) -> dict | None:
    hay = _buyer_text(company, research, lead)
    hay_tokens = tokenize(hay)
    division_name = (product.division_name or "").strip()

    product_blob = " ".join(
        filter(
            None,
            [
                product.name, product.category, product.description, product.applications,
                product.target_industries, product.ideal_buyer_types, product.specifications,
                # service_area is a location filter (geo_ok below), not a keyword.
                division_name,
            ],
        )
    ).lower()
    overlap = hay_tokens & tokenize(product_blob)

    # A phrase "hits" when all its (stemmed) words appear in the buyer's text.
    industry_hit = False
    if product.target_industries:
        for part in re.split(r"[,;/|]", product.target_industries.lower()):
            words = tokenize(part)
            if words and words <= hay_tokens:
                industry_hit = True
                overlap.add("".join(sorted(words)))

    app_hit = False
    if product.applications:
        for part in re.split(r"[,;/|]", product.applications.lower()):
            words = tokenize(part)
            if len(part.strip()) > 3 and words and words <= hay_tokens:
                app_hit = True

    geo_ok = True
    if product.service_area and company.country:
        area = product.service_area.lower()
        if "global" not in area and "worldwide" not in area and "all" not in area and len(area) > 2:
            geo_ok = company.country.lower() in area

    if product.exclusions:
        for part in re.split(r"[,;/|]", product.exclusions.lower()):
            part = part.strip()
            if len(part) > 3 and part in hay:
                return None

    name_tokens = tokenize(product.name)
    name_hit = bool(name_tokens & hay_tokens)

    score = min(len(overlap), 12) * 6.0
    if industry_hit:
        score += 25
    if app_hit:
        score += 20
    if name_hit:
        score += 18
    if research and research.facilities:
        fac = research.facilities.lower()
        score += 12 * sum(1 for token in name_tokens if token in fac)
    if not geo_ok:
        score *= 0.4

    primary = False
    if lead and lead.lead_type == "inbound":
        req = " ".join(filter(None, [lead.interested_product, lead.requirement_description])).lower()
        asked_division = (lead.interested_division or "").strip().lower()
        in_division = bool(division_name) and division_name.lower() == asked_division
        if lead.interested_product:
            # A specific product was asked for: only lines matching it are the
            # stated requirement. The rest of its division is a cross-sell.
            if product.name.lower() in req and (in_division or not asked_division):
                primary, score = True, max(score, 80)
            elif not exact_line_requested and in_division and tokenize(lead.interested_product) & name_tokens:
                # Fuzzy match, only when the request names no exact catalogue line.
                primary, score = True, max(score, 75)
            elif in_division:
                score += 10
        elif in_division or (division_name and division_name.lower() in req):
            # Only a division was given: the whole division is the requirement.
            primary, score = True, max(score, 70)

    if score < 18 and not primary:
        return None

    if score >= 70 or (industry_hit and app_hit):
        confidence = "High"
    elif score >= 40 or industry_hit or app_hit:
        confidence = "Medium"
    else:
        confidence = "Low"

    sources = (research.sources if research else None) or []
    evidence_url = sources[0] if sources else company.website

    if primary:
        rec_type = "primary_requirement"
        verification = "confirmed_request"
        reason = f"The buyer explicitly requested {lead.interested_product or lead.interested_division}."
        activity = lead.application or lead.requirement_description or "Stated inbound requirement"
        sales_verify = "Confirm quantity, specifications, and delivery timeline with the buyer."
    else:
        rec_type = "cross_sell" if lead and lead.lead_type == "inbound" else "potential_opportunity"
        verification = "potential"
        why = []
        if industry_hit:
            why.append(f"industry alignment with {company.industry or 'the company sector'}")
        if app_hit:
            why.append("matching application keywords")
        if name_hit:
            why.append("direct mention of related equipment or capability")
        if not why:
            why.append("partial keyword overlap with catalogue attributes")
        reason = "Possible fit based on " + " and ".join(why) + "."
        if confidence == "Low":
            reason += " This is a general industry-level possibility with limited supporting evidence."
        activity = (research.business_activities if research else None) or company.industry
        sales_verify = "Verify actual requirement, installed equipment, and buying authority before outreach."

    evidence_summary = (
        f"Matched terms: {', '.join(sorted(overlap)[:8]) or 'limited'}. "
        f"Evidence: {'company website' if research and research.website_read else 'company-provided details only'}."
    )
    return {
        "product": product,
        "score": round(min(score, 100.0), 1),
        "raw_score": score,
        "confidence": confidence,
        "recommendation_type": rec_type,
        "verification_status": verification,
        "reason": reason,
        "activity": activity,
        "evidence_summary": evidence_summary,
        "evidence_url": evidence_url,
        "sales_verify": sales_verify,
        "primary": primary,
    }


def _narrow_division_request(lead, scored: list[dict]) -> None:
    """Only a division was named ("Lighting"): if the customer's own words point at
    particular lines ("LED replacements for car park lights"), only those are the
    requirement and the rest of the division becomes suggestions. Without such
    words the whole division stays requested."""
    words = tokenize(" ".join(filter(None, [lead.requirement_description, lead.application, lead.technical_requirements])))
    candidates = [s for s in scored if s["primary"]]
    if not words or not candidates:
        return
    def line_words(s) -> set[str]:
        p = s["product"]
        return tokenize(" ".join(filter(None, [p.name, p.applications, p.category])))

    # Words naming the division ("lighting") or shared by half its lines
    # ("replacement") don't single out a line.
    generic = set().union(*(tokenize(s["product"].division_name) for s in candidates))
    if len(candidates) >= 3:
        counts: dict[str, int] = {}
        for s in candidates:
            for w in line_words(s):
                counts[w] = counts.get(w, 0) + 1
        generic |= {w for w, n in counts.items() if n * 2 >= len(candidates)}

    def hits(s) -> set[str]:
        return (words & line_words(s)) - generic

    named = [s for s in candidates if hits(s)]
    if not named or len(named) == len(candidates):
        return
    for s in candidates:
        h = hits(s)
        if h:
            s["reason"] = f"Matches what the buyer described ({', '.join(sorted(h))}) in the requested {lead.interested_division} range."
            continue
        s.update(
            primary=False,
            recommendation_type="cross_sell",
            verification_status="potential",
            reason=f"Also in the requested {lead.interested_division} range, but not what the buyer described.",
            sales_verify="Offer only if relevant to the stated requirement.",
            raw_score=s["raw_score"] - 40,
        )


def match_products(company, research, lead, products: list) -> list[dict]:
    """Best catalogue lines for this buyer, requested lines first."""
    active = [p for p in products if p.is_active and p.division_active]
    requested = ((lead.interested_product if lead else None) or "").strip().lower()
    requested_division = ((lead.interested_division if lead else None) or "").strip().lower()
    exact_line_requested = bool(requested) and any(
        p.name.lower() == requested and (not requested_division or (p.division_name or "").lower() == requested_division)
        for p in active
    )
    scored = [s for s in (score_product(company, research, p, lead, exact_line_requested) for p in active) if s]
    # Rank on the uncapped score: many lines reach the displayed 100 for a rich profile.
    scored.sort(key=lambda x: (-int(x["primary"]), -x["raw_score"]))
    if lead and lead.lead_type == "inbound" and not requested and requested_division:
        _narrow_division_request(lead, scored)
        scored.sort(key=lambda x: (-int(x["primary"]), -x["raw_score"]))
    primary = [s for s in scored if s["primary"]]
    others = [s for s in scored if not s["primary"]]
    # Cross-selling is about breadth: at most MAX_PER_DIVISION suggestions from
    # one division first, then fill any remaining places by score.
    picked, per_division, overflow = [], {}, []
    for s in others:
        div = s["product"].division_name
        if per_division.get(div, 0) < MAX_PER_DIVISION:
            per_division[div] = per_division.get(div, 0) + 1
            picked.append(s)
        else:
            overflow.append(s)
    room = max(0, MAX_RECOMMENDATIONS - len(primary))
    chosen = (picked + overflow)[:room]
    chosen.sort(key=lambda x: -x["raw_score"])
    return primary + chosen
