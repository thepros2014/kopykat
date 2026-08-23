"""models.py — Pydantic request/response models for the FastAPI layer."""

from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, EmailStr, Field

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    plan: str
    generations: int

class UserProfile(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    plan: str
    generations: int
    monthly_limit: int
    created_at: datetime
    class Config:
        from_attributes = True

class APIKeyCreate(BaseModel):
    name: str = Field(default="My Key", max_length=100)

class APIKeyResponse(BaseModel):
    id: str
    key_prefix: str
    name: str
    is_active: bool
    last_used: Optional[datetime]
    requests_today: int
    created_at: datetime
    class Config:
        from_attributes = True

class APIKeyCreated(APIKeyResponse):
    raw_key: str

COPY_TYPES = Literal[
    "product_description", "email_subject", "email_body", "social_post",
    "ad_headline", "ad_body", "landing_page_hero", "call_to_action",
    "seo_meta_description", "blog_intro",
]

class GenerateRequest(BaseModel):
    type: COPY_TYPES
    context: str = Field(min_length=5, max_length=2000)
    tone: Optional[Literal["professional", "casual", "urgent", "friendly", "bold"]] = "professional"
    variations: int = Field(default=1, ge=1, le=5)
    max_words: int = Field(default=300, ge=50, le=1000)

class GenerateResponse(BaseModel):
    type: str
    variations: List[str]
    generations_used: int
    generations: int
    generation_time_ms: int

class CheckoutRequest(BaseModel):
    plan: Literal["boutique", "standard", "megastore"]

class OneTimeGenerationsRequest(BaseModel):
    tier: Literal["starter", "growth", "scale"]

class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str

class SubscriptionStatus(BaseModel):
    plan: str
    status: str
    current_period_end: Optional[datetime]
    generations: int
    monthly_limit: int

class UsageSummary(BaseModel):
    total_requests: int
    total_generations_used: int
    generations: int
    monthly_limit: int
    plan: str
    period_start: Optional[str]
    period_end: Optional[str]

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime

class RequestPasswordReset(BaseModel):
    email: EmailStr

class ResetPasswordSubmit(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=72)

class IntegrationSaveRequest(BaseModel):
    platform: Literal["wordpress", "mailchimp", "hubspot", "shopify", "webflow", "amazon", "ebay", "walmart", "temu"]
    credentials: dict

class PushRequest(BaseModel):
    platform: Literal["wordpress", "mailchimp", "hubspot", "shopify", "webflow", "amazon", "ebay", "walmart", "temu"]
    content: str
    title: Optional[str] = "Generated via KopyKat"
    metadata: Optional[dict] = None

class CampaignGenerateRequest(BaseModel):
    keyword: str = Field(min_length=2, max_length=100)
    product_desc: str = Field(min_length=2, max_length=1000)

class CampaignPushRequest(BaseModel):
    campaign_id: str
    destinations: dict


class ConnectorDiscoverRequest(BaseModel):
    url: str = Field(min_length=5, max_length=2000)

class ConnectorResponse(BaseModel):
    id: str
    platform_name: str
    base_url: str
    operation_count: int
    authentication_modes: list[str]
    status: str


class RequestVerificationRequest(BaseModel):
    email: EmailStr

class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=10, max_length=128)

class ConnectorCredentialsRequest(BaseModel):
    credentials: dict

class ConnectorTestRequest(BaseModel):
    operation_name: str
    headers: Optional[dict] = None
    query: Optional[dict] = None

class ConnectorToggleRequest(BaseModel):
    active: bool

class CampaignVisionGenerateRequest(BaseModel):
    keyword: Optional[str] = ""
    extra_context: Optional[str] = ""
    image_base64: str = Field(min_length=10)
    mime_type: Optional[str] = "image/jpeg"
