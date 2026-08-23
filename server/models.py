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


class CompetitorMineRequest(BaseModel):
    product_name: str = Field(min_length=2, max_length=200)
    competitor_name: Optional[str] = Field(default="Competitor", max_length=200)
    reviews_text: str = Field(min_length=10, max_length=10000)

class CompetitorMineResponse(BaseModel):
    id: str
    product_name: str
    competitor_name: str
    extracted_flaws: list[str]
    counter_description: str
    comparison_points: list[dict]
    ad_hooks: list[str]


class CustomAIKeyRequest(BaseModel):
    api_key: str = Field(min_length=10, max_length=500)
    provider: Literal["openai", "gemini"] = "openai"

class CustomAIKeyResponse(BaseModel):
    has_custom_key: bool
    provider: Optional[str] = None
    unlimited_active: bool


class InventoryItemCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=255)
    total_stock: int = Field(ge=0)

class InventoryItemResponse(BaseModel):
    id: str
    sku: str
    title: str
    total_stock: int
    platform_stock: dict
    updated_at: datetime

class InventoryWebhookPayload(BaseModel):
    sku: str
    quantity_delta: int  # e.g. -1 for a sale, +10 for a restock
    order_id: Optional[str] = None
    customer_email: Optional[str] = None

class InventorySyncLogResponse(BaseModel):
    id: str
    sku: str
    trigger_platform: str
    quantity_change: int
    new_quantity: int
    fanout_results: dict
    created_at: datetime


class PostPurchaseDripRequest(BaseModel):
    product_name: str = Field(min_length=2, max_length=200)
    brand_tone: Optional[str] = "Warm, grateful, and helpful"
    incentive_offer: Optional[str] = "15% off your next purchase"

class PostPurchaseDripResponse(BaseModel):
    id: str
    product_name: str
    drip_emails: list[dict]  # list of {step: int, day: int, subject: str, body: str, goal: str}

class CustomerReviewSubmitRequest(BaseModel):
    customer_name: str = Field(min_length=1, max_length=100)
    customer_email: Optional[str] = None
    product_name: str = Field(min_length=2, max_length=255)
    rating: int = Field(ge=1, le=5)
    review_text: str = Field(min_length=5, max_length=5000)

class CustomerReviewResponse(BaseModel):
    id: str
    customer_name: str
    customer_email: Optional[str] = None
    product_name: str
    rating: int
    review_text: str
    sentiment: str
    status: str
    draft_reply: Optional[str] = None
    created_at: datetime


class PriceMarginItemCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    product_name: str = Field(min_length=1, max_length=255)
    cogs_usd: float = Field(ge=0.0)
    selling_price_usd: float = Field(gt=0.0)
    competitor_price_usd: Optional[float] = None
    target_margin_pct: Optional[float] = 40.0

class PriceMarginItemResponse(BaseModel):
    id: str
    sku: str
    product_name: str
    cogs_usd: float
    selling_price_usd: float
    competitor_price_usd: Optional[float] = None
    target_margin_pct: float
    current_margin_pct: float
    profit_per_unit_usd: float
    status: str
    recommendation: str
    updated_at: datetime


class ShopifyImportRequest(BaseModel):
    shop_url: Optional[str] = None
    access_token: Optional[str] = None
    limit: Optional[int] = 50

class ShopifyImportResponse(BaseModel):
    success: bool
    total_imported: int
    items: list[dict]
    error: Optional[str] = None
