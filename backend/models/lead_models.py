from pydantic import BaseModel, Field
from typing import List, Optional

class Lead(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = Field(default="")
    title: Optional[str] = Field(default="")
    company: Optional[str] = Field(default="")
    email: Optional[str] = Field(default="")
    phone: Optional[str] = Field(default="")
    website: Optional[str] = Field(default="")
    location: Optional[str] = Field(default="")
    linkedin: Optional[str] = Field(default="", alias="linkedIn")
    linkedIn: Optional[str] = Field(default="")
    segment: Optional[str] = Field(default="")
    priority: Optional[str] = Field(default="")
    channel: Optional[str] = Field(default="")
    division: Optional[str] = Field(default="Not Specified")
    email_sent: Optional[bool] = Field(default=False)
    email_sent_date: Optional[str] = Field(default=None)
    email_status: Optional[str] = Field(default=None)
    email_error: Optional[str] = Field(default=None)

    class Config:
        populate_by_name = True

class LeadsRequest(BaseModel):
    leads: List[Lead]

class GenerateLeadsInput(BaseModel):
    division: Optional[str] = Field(default="Not Specified")
    productName: str
    brand: Optional[str] = Field(default="Not Specified")
    description: Optional[str] = Field(default="Not Specified")


class SingleEmailRequest(BaseModel):
    email: str
    subject: str
    body: str


class BulkEmailRequest(BaseModel):
    leadIds: Optional[List[int]] = None
    leads: Optional[List[Lead]] = None
    subject: str
    body: str
    delay: Optional[float] = 2.0


class EmailTemplateSchema(BaseModel):
    id: Optional[int] = None
    template_name: str
    subject: str
    body: str

