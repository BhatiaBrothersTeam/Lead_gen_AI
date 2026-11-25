"""Request bodies. Field names match LeadMatch's API, which the website already sends."""
from __future__ import annotations

from pydantic import BaseModel, Field


def _s(n: int):
    return Field(default=None, max_length=n)


class EnquiryIn(BaseModel):
    """One inbound enquiry: from the website (POST /api/public/enquiry) or typed in by sales.

    Only a way to reach the customer (business_email or phone_number) is
    required; everything else is optional and missing details are flagged on the lead.
    """

    company_name: str | None = _s(255)
    contact_person: str | None = _s(255)
    business_email: str | None = _s(255)
    phone_number: str | None = _s(64)
    country: str | None = _s(128)
    city: str | None = _s(128)
    interested_division: str | None = _s(255)
    company_website: str | None = _s(1024)
    industry: str | None = _s(255)
    product_service: str | None = _s(500)
    quantity: str | None = _s(128)
    application: str | None = _s(2000)
    technical_requirements: str | None = _s(4000)
    timeline: str | None = _s(128)
    requirement_description: str | None = _s(8000)
    additional_notes: str | None = _s(8000)
    source: str | None = _s(255)
    campaign: str | None = _s(255)
    whatsapp_same_as_phone: bool = False
    utm_source: str | None = _s(255)
    utm_medium: str | None = _s(255)
    utm_campaign: str | None = _s(255)
    utm_content: str | None = _s(255)
    utm_term: str | None = _s(255)
    landing_page: str | None = _s(1024)
    referrer: str | None = _s(1024)
    form_version: str | None = _s(32)
    # The sender's own reference (e.g. the website's VVS-… number): resending it returns the same lead.
    external_reference: str | None = _s(64)


class ProspectIn(BaseModel):
    """One outbound prospect added by hand. Only the company name is required."""

    company_name: str = Field(min_length=1, max_length=255)
    country: str | None = _s(128)
    city: str | None = _s(128)
    website: str | None = _s(1024)
    industry: str | None = _s(255)
    description: str | None = _s(4000)
    contact_person: str | None = _s(255)
    designation: str | None = _s(255)
    email: str | None = _s(255)
    phone: str | None = _s(64)
    whatsapp: str | None = _s(64)
    notes: str | None = _s(4000)
    source: str | None = _s(255)


class FeedbackIn(BaseModel):
    verdict: str  # "relevant" | "irrelevant" | "" (clear)


class FollowUpIn(BaseModel):
    follow_up_status: str


class DraftIn(BaseModel):
    # Catalogue suggestions sales chose to include (requested lines are always included).
    recommendation_ids: list[str] = Field(default_factory=list, max_length=12)
    personalize: bool = False


class SendEmailIn(BaseModel):
    recipient: str = Field(min_length=3, max_length=255)
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=20000)


class WhatsAppLogIn(BaseModel):
    number: str = Field(min_length=6, max_length=32)
