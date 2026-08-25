"""models.py — Pydantic request/response models for the FastAPI layer."""

from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: Optional[str] = Field(default=None, max_length=255)

class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    plan: str
    generations: int

class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    full_name: Optional[str]
    plan: str
    generations: int
    monthly_limit: int
    created_at: datetime

class APIKeyCreate(BaseModel):
    name: str = Field(default="My Key", min_length=1, max_length=100)

class APIKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    key_prefix: str
    name: str
    is_active: bool
    last_used: Optional[datetime]
    requests_today: int
    created_at: datetime

class APIKeyCreated(APIKeyResponse):
    raw_key: str

class PublicMetricsSummary(BaseModel):
    total_campaigns_generated: int
    supported_marketplaces_count: int
    active_subscribers_mrr_usd: float
    estimated_seller_hours_saved: int
    # Uptime is intentionally nullable until it is backed by a real monitor.
    platform_uptime_pct: Optional[float] = None
    api_version: str = "2.0.0"

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
    output: Optional[str] = None
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


class PartnerPlacementCheckoutRequest(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    placement_type: Literal["featured", "directory"]
    slot: int = Field(ge=1, le=8)
    interval: Literal["monthly", "yearly"]
    logo_url: Optional[str] = Field(default=None, max_length=2_000)
    service_url: Optional[str] = Field(default=None, max_length=2_000)


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
    byok_server_activity_used: int = 0
    byok_server_activity_limit: int = 0
    byok_server_activity_remaining: int = 0
    byok_server_activity_reset_at: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime

class RequestPasswordReset(BaseModel):
    email: EmailStr

class ResetPasswordSubmit(BaseModel):
    token: str = Field(min_length=10, max_length=128)
    new_password: str = Field(min_length=8, max_length=72)

class IntegrationSaveRequest(BaseModel):
    platform: Literal["wordpress", "mailchimp", "hubspot", "shopify", "webflow", "amazon", "ebay", "walmart", "temu"]
    credentials: dict

class PushRequest(BaseModel):
    platform: Literal["wordpress", "mailchimp", "hubspot", "shopify", "webflow", "amazon", "ebay", "walmart", "temu"]
    content: str = Field(min_length=1, max_length=100_000)
    title: Optional[str] = Field(default="Generated via KopyKat", max_length=255)
    metadata: Optional[dict] = None

class CampaignGenerateRequest(BaseModel):
    keyword: str = Field(min_length=2, max_length=100)
    product_desc: str = Field(min_length=2, max_length=1000)

class CampaignPushRequest(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=100)
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
    operation_name: str = Field(min_length=1, max_length=120)
    headers: Optional[dict] = None
    query: Optional[dict] = None

class ConnectorToggleRequest(BaseModel):
    active: bool

class CampaignVisionGenerateRequest(BaseModel):
    keyword: Optional[str] = Field(default="", max_length=500)
    extra_context: Optional[str] = Field(default="", max_length=2_000)
    # 15 MB of base64 is a generous ceiling while preventing an unbounded
    # request body from being copied into memory and sent to an AI provider.
    image_base64: str = Field(min_length=1, max_length=15_000_000)
    mime_type: Optional[str] = Field(default="image/jpeg", max_length=64)


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
    server_activity_used: int = 0
    server_activity_limit: int = 0
    server_activity_remaining: int = 0
    server_activity_reset_at: Optional[str] = None


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
    sku: str = Field(min_length=1, max_length=100)
    quantity_delta: int = Field(ge=-2_000_000, le=2_000_000)  # e.g. -1 for a sale, +10 for a restock
    order_id: Optional[str] = Field(default=None, max_length=100)
    customer_email: Optional[str] = Field(default=None, max_length=255)

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
    brand_tone: Optional[str] = Field(default="Warm, grateful, and helpful", max_length=500)
    incentive_offer: Optional[str] = Field(default="15% off your next purchase", max_length=500)

class PostPurchaseDripResponse(BaseModel):
    id: str
    product_name: str
    drip_emails: list[dict]  # list of {step: int, day: int, subject: str, body: str, goal: str}

class CustomerReviewSubmitRequest(BaseModel):
    customer_name: str = Field(min_length=1, max_length=100)
    customer_email: Optional[EmailStr] = None
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
    competitor_price_usd: Optional[float] = Field(default=None, ge=0.0)
    target_margin_pct: Optional[float] = Field(default=40.0, ge=0.0, le=100.0)

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
    shop_url: Optional[str] = Field(default=None, max_length=255)
    access_token: Optional[str] = Field(default=None, max_length=500)
    limit: int = Field(default=50, ge=1, le=250)

class ShopifyImportResponse(BaseModel):
    success: bool
    total_imported: int
    items: list[dict]
    error: Optional[str] = None

# --- À-LA-CARTE MONETIZATION & ADD-ON SCHEMAS ---

class BrandPersonaRequest(BaseModel):
    brand_name: str = Field(min_length=1, max_length=255)
    brand_voice_tone: str = Field(min_length=2, max_length=255)
    target_audience: Optional[str] = Field(default=None, max_length=500)
    rules_and_guidelines: Optional[str] = Field(default=None, max_length=5_000)
    sample_copy: Optional[str] = Field(default=None, max_length=5_000)

class BrandPersonaResponse(BaseModel):
    id: str
    brand_name: str
    brand_voice_tone: str
    target_audience: Optional[str] = None
    rules_and_guidelines: Optional[str] = None
    sample_copy: Optional[str] = None
    updated_at: datetime


class MarketplaceOptimizeRequest(BaseModel):
    product_name: str = Field(min_length=2, max_length=255)
    platform: str = Field(pattern="^(amazon|shopify|etsy|tiktok|tiktok_shop|ebay)$")
    raw_details: str = Field(min_length=5, max_length=5000)
    keywords: Optional[str] = Field(default=None, max_length=1_000)
    target_audience: Optional[str] = Field(default=None, max_length=500)

class MarketplaceOptimizeResponse(BaseModel):
    platform: str
    product_name: str
    optimized_title: str
    bullet_points: list[str] = Field(default_factory=list)
    meta_description: Optional[str] = None
    backend_search_terms: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    short_hooks: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    sub_title: Optional[str] = None
    item_specifics: Optional[dict] = None
    structured_description: str
    compliance_score: int  # 1-100 score on platform character limits & keyword density


class AddOnCheckoutRequest(BaseModel):
    addon_key: str = Field(min_length=2, max_length=50)

class AddOnItemResponse(BaseModel):
    key: str
    name: str
    price_usd: float
    billing_type: str  # one_time / monthly
    description: str
    features: list[str]


# --- GROWTH ENGINE & MRR TELEMETRY SCHEMAS ---

class AdminMRRMetricsResponse(BaseModel):
    mrr_usd: float
    arr_usd: float
    active_subscribers: int
    canceled_subscribers: int
    past_due_subscribers: int
    churn_rate_pct: float
    active_subscribers_by_tier: dict
    total_lifetime_revenue_usd: float
    total_registered_merchants: int
    pricing_model: dict
    # A subjective valuation score is not a financial fact. Keep it nullable
    # until an explicit, documented scoring model exists.
    software_asset_score: Optional[float] = None
    valuation_estimate_usd: dict

class SEOAnalyticsArticle(BaseModel):
    id: str
    title: str
    slug: str
    url: str
    word_count: int
    created_at: datetime

class SEOAnalyticsResponse(BaseModel):
    total_posts: int
    total_words_generated: int
    sitemap_url: str
    robots_url: str
    indexing_status: str
    recent_articles: list[SEOAnalyticsArticle]

class SEOPingIndexResponse(BaseModel):
    success: bool
    sitemap_url: str
    pings: list[dict]
    message: str

class OpportunityLeadItemResponse(BaseModel):
    id: str
    platform: str
    post_title: str
    post_url: str
    draft_reply: str
    score: int
    created_at: datetime

class DripAnalyticsFunnel(BaseModel):
    total_free_users: int
    day2_value_drips_sent: int
    day4_case_study_drips_sent: int
    day7_upgrade_drips_sent: int
    active_paying_subscribers: int

class DripAnalyticsResponse(BaseModel):
    funnel: DripAnalyticsFunnel
    conversion_rate_pct: float
    status: str

