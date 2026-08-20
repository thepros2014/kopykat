"""
models.py — Pydantic request/response models for the FastAPI layer.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, EmailStr, Field


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
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


# ── API Keys ──────────────────────────────────────────────────────────────────

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
    """Returned only once at creation — includes the full raw key."""
    raw_key: str


# ── AI Generation ─────────────────────────────────────────────────────────────

COPY_TYPES = Literal[
    "product_description",
    "email_subject",
    "email_body",
    "social_post",
    "ad_headline",
    "ad_body",
    "landing_page_hero",
    "call_to_action",
    "seo_meta_description",
    "blog_intro",
]

class GenerateRequest(BaseModel):
    type: COPY_TYPES
    context: str = Field(
        min_length=5,
        max_length=2000,
        description="Describe your product/service, tone, and target audience."
    )
    tone: Optional[Literal["professional", "casual", "urgent", "friendly", "bold"]] = "professional"
    variations: int = Field(default=1, ge=1, le=5)
    max_words: int = Field(default=300, ge=50, le=1000)


class GenerateResponse(BaseModel):
    type: str
    variations: List[str]
    generations_used: int
    generations: int
    generation_time_ms: int


# ── Billing ───────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: Literal["basic", "pro", "business"]


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


# ── Usage & Analytics ─────────────────────────────────────────────────────────

class UsageSummary(BaseModel):
    total_requests: int
    total_generations_used: int
    generations: int
    monthly_limit: int
    plan: str
    period_start: Optional[str]
    period_end: Optional[str]


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime
class RequestPasswordReset(BaseModel):
    email: EmailStr

class ResetPasswordSubmit(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)

class IntegrationSaveRequest(BaseModel):
    platform: Literal["wordpress", "mailchimp", "hubspot", "shopify", "webflow"]
    credentials: dict

class PushRequest(BaseModel):
    platform: Literal["wordpress", "mailchimp", "hubspot", "shopify", "webflow"]
    content: str
    title: Optional[str] = "Generated via SnapCopy AI"
    metadata: Optional[dict] = {}

class CampaignGenerateRequest(BaseModel):
    keyword: str = Field(min_length=2, max_length=100)
    product_desc: str = Field(min_length=10, max_length=1000)

class CampaignPushRequest(BaseModel):
    campaign_id: str
    destinations: dict  # e.g. {"blog": {"platform": "wordpress", "metadata": {"category_id": "1"}}}
