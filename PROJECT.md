# Project: KopyKat Enterprise Expansion

## Architecture
KopyKat is an enterprise-grade multi-modal e-commerce syndication and automated growth platform built on Python 3.11, FastAPI (ASGI), SQLAlchemy 2.0 ORM, and APScheduler.

```
c:\Users\plumb\Desktop\claude-project\
├── server/
│   ├── main.py                  # FastAPI app, routing, middleware, lifespan, admin & auth endpoints
│   ├── database.py              # SQLAlchemy 2.0 models (User, Subscription, Connectors, Inventory, etc.)
│   ├── models.py                # Pydantic v2 schemas for request/response validation
│   ├── auth.py                  # Bcrypt (72-byte capped), JWT HS256, Fernet encryption
│   ├── billing.py               # Stripe integration, dual-bucket quotas, entitlements, webhooks
│   ├── campaigns.py             # Multimodal vision (Gemini/OpenAI) & omni-channel campaigns
│   ├── ai_engine.py             # Listing optimizer (Amazon, Shopify, Etsy, TikTok Shop, eBay), review miner
│   ├── connector_engine.py      # OpenAPI spec discovery, SafeAsyncHTTPClient, SSRF/DNS rebinding defense
│   ├── connector_registry.py    # Async connector execution runtime with IP-pinned transport
│   ├── integrations.py          # Platform connectors (Amazon, Shopify, Etsy, TikTok Shop, eBay)
│   ├── inventory.py             # Inventory balancing, loop-free fanout, drift reconciliation, idempotency
│   ├── marketing.py             # SEO blog generation, sitemap/robots, Reddit lead scout, drip emails
│   ├── reviews_ugc.py           # Review sentiment classifier, merchant draft replies, UGC drips
│   ├── content_governance.py    # Brand safety, anti-defamation, claims filters
│   └── scheduler.py             # Background automation cron tasks
├── frontend/
│   ├── index.html, dashboard.html, admin.html, blog.html, post.html
│   └── static/ (styles.css, api.js)
└── tests/                       # Pytest test suites across all functional tiers
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F1 | Multi-Modal Vision Pipeline | Image-based product analysis and omni-channel campaign generation via Gemini/OpenAI with atomic balance reservation & failure refund | M1 | ORIGINAL_REQUEST §1 |
| F2 | Amazon Listing Schema | Structured output: Title <200 chars, 5 bullet points, backend keywords <249 bytes, compliance score, fallback | M1 | ORIGINAL_REQUEST §1 |
| F3 | Shopify Listing Schema | Structured output: Title <70 chars, meta description <155 chars, 4 bullets, DTC HTML description, compliance score, fallback | M1 | ORIGINAL_REQUEST §1 |
| F4 | Etsy Listing Schema | Structured output: Title <140 chars, 13 long-tail tags (<20 chars), 3-4 bullets, warm artisan description, compliance score, fallback | M1 | ORIGINAL_REQUEST §1 |
| F5 | TikTok Shop Listing Schema | Structured output: Title <100 chars, viral hooks, video script teasers, 5-8 hashtags, mobile description, compliance score, fallback | M1 | ORIGINAL_REQUEST §1 |
| F6 | eBay Listing Schema | Structured output: Title <80 chars, subtitle <55 chars, item specifics dict, 3-4 bullets, listing template, compliance score, fallback | M1 | ORIGINAL_REQUEST §1 |
| F7 | Autonomous Platform Connectors | Standardized async connector clients for Amazon, Shopify, Etsy, TikTok Shop, eBay | M2 | ORIGINAL_REQUEST §2 |
| F8 | Real-Time Sync & Fanout Engine | Bi-directional inventory & product catalog sync, loop-free fanout, stock drift reconciliation | M2 | ORIGINAL_REQUEST §2 |
| F9 | Webhook Idempotency Ledger | Idempotent webhook processing on unique `(platform, event_id)` preventing replay stock debits | M2 | ORIGINAL_REQUEST §2 |
| F10 | Non-Blocking Async HTTP & SSRF Defense | SafeAsyncHTTPClient with IP pre-resolution, socket pinning, SNI preservation, redirect blocking, 2MB streaming cap | M2 | ORIGINAL_REQUEST §2 |
| F11 | SEO Blog Generation Engine | Automated keyword-driven blog posts with sanitized HTML, sitemap.xml, robots.txt, ping-index | M3 | ORIGINAL_REQUEST §3 |
| F12 | Review Sentiment & UGC Drips | 3-step post-purchase review drips, sentiment classification (pos/neu/neg), automated draft resolution replies | M3 | ORIGINAL_REQUEST §3 |
| F13 | Lead Gen & Competitor Mining | Reddit opportunity scout with intent scoring (75-99) & draft replies; 1-star competitor review flaw miner | M3 | ORIGINAL_REQUEST §3 |
| F14 | Admin Revenue & MRR Telemetry | Backend `/admin/mrr-metrics` calculating MRR, ARR, tier breakdown, lifetime revenue, asset valuation | M3 | ORIGINAL_REQUEST §3 |
| F15 | Security & Tenant Isolation | Scoped ORM queries (`user_id == user.id`), Fernet credential encryption, bcrypt max 72 bytes | M4 | ORIGINAL_REQUEST §4 |
| F16 | Subscription Entitlements & BYOK | Entitlement checks for à-la-carte add-ons, BYOK gating restricted to Megastore tier | M4 | ORIGINAL_REQUEST §4 |
| F17 | Financial Invariants & Quota Accounting | Dual-bucket balance model, centralized `reserve_user_generations` / `refund_user_generations`, HTTP 503 on unconfigured Stripe | M4 | ORIGINAL_REQUEST §4 |
| F18 | Zero-Emoji Invariant | Complete zero-emoji policy compliance across server and frontend codebases | M4 | ORIGINAL_REQUEST §4 |
| F19 | Frontend Dashboard & Admin UI | Complete HTML `<section>` blocks for all 9 tools in dashboard.html; MRR/ARR telemetry in admin.html | M4 | ORIGINAL_REQUEST §Mission |
| F20 | E2E Testing Suite (Tiers 1-4) | Comprehensive opaque-box test suite covering feature tests, boundaries, pairwise interactions, real scenarios | E2E_TRACK | ORIGINAL_REQUEST §Acceptance |
| F21 | Final Verification & Hardening | 100% E2E test pass + Tier 5 adversarial white-box coverage hardening | M_FINAL | ORIGINAL_REQUEST §Acceptance |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Multi-Modal Campaign & Platform Schemas | F1, F2, F3, F4, F5, F6 | none | DONE |
| M2 | Autonomous Connectors, Sync & SSRF Defense | F7, F8, F9, F10 | none | DONE |
| M3 | Automated Growth Engine & Telemetry | F11, F12, F13, F14 | none | DONE |
| M4 | Security Governance, Financial Invariants & Frontend UI | F15, F16, F17, F18, F19 | M1, M2, M3 | DONE |
| E2E | E2E Testing Suite Track | F20 (Tiers 1-4 Test Suite: 190 tests) | none | DONE |
| M_FINAL | E2E Test Pass & Adversarial Hardening | F21 (100% E2E Pass + Tier 5 Hardening) | M4, E2E | IN_PROGRESS |

## Interface Contracts

### 1. Listing Optimizer Contract (`server/ai_engine.py`)
```python
def optimize_marketplace_listing(
    product_name: str,
    platform: str,  # "amazon" | "shopify" | "etsy" | "tiktok" | "tiktok_shop" | "ebay"
    raw_details: str = "",
    keywords: str = "",
    target_audience: str = "",
    brand_persona: Optional[dict] = None
) -> dict:
    """
    Returns platform-tailored dictionary:
    - Amazon: {"optimized_title": str, "bullet_points": list[str] (5), "backend_search_terms": str, "structured_description": str, "compliance_score": int}
    - Shopify: {"optimized_title": str, "meta_description": str, "bullet_points": list[str] (4), "structured_description": str, "compliance_score": int}
    - Etsy: {"optimized_title": str, "tags": list[str] (13), "bullet_points": list[str], "structured_description": str, "compliance_score": int}
    - TikTok: {"optimized_title": str, "short_hooks": list[str], "bullet_points": list[str], "hashtags": list[str], "structured_description": str, "compliance_score": int}
    - eBay: {"optimized_title": str, "sub_title": str, "item_specifics": dict, "bullet_points": list[str], "structured_description": str, "compliance_score": int}
    """
```

### 2. Universal Platform Connector Contract (`server/integrations.py`)
```python
class PlatformConnector(Protocol):
    platform_name: str
    async def fetch_catalog(self, credentials: dict, limit: int = 50) -> list[dict]: ...
    async def push_product(self, credentials: dict, product_data: dict) -> dict: ...
    async def update_stock(self, credentials: dict, sku: str, quantity: int) -> dict: ...
    def verify_webhook(self, headers: dict, raw_payload: bytes, secret: str) -> bool: ...
```

### 3. Safe Async HTTP Client Contract (`server/connector_engine.py`)
```python
class SafeAsyncHTTPClient:
    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[dict] = None,
        json_body: Optional[Any] = None,
        params: Optional[dict] = None,
        timeout_seconds: float = 15.0,
        max_response_bytes: int = 2_000_000,
        allow_redirects: bool = False
    ) -> SafeHTTPResponse:
        """Enforces DNS pre-resolution, private IP rejection, socket pinning, SNI header preservation, redirect rejection, and 2MB payload cap."""
```

### 4. Quota Accounting Contract (`server/main.py`)
```python
def reserve_user_generations(user_id: int, cost: int, db: Session) -> tuple[int, int]:
    """Reserves 'cost' credits prioritizing monthly_generations before purchased_generations using row locking."""

def refund_user_generations(user_id: int, monthly_refund: int, purchased_refund: int, db: Session) -> None:
    """Restores reserved credits to user's monthly and purchased buckets upon upstream failure."""
```

## Code Layout
- `server/ai_engine.py`: Multi-platform listing optimization (Amazon, Shopify, Etsy, TikTok Shop, eBay), review flaw miner.
- `server/campaigns.py`: Multi-modal vision generation and omni-channel campaigns.
- `server/models.py`: Pydantic validation schemas (`MarketplaceOptimizeRequest`, `CampaignVisionGenerateRequest`, etc.).
- `server/connector_engine.py`: SafeAsyncHTTPClient, URL validation, OpenAPI spec discovery.
- `server/connector_registry.py`: Async connector execution runtime.
- `server/integrations.py`: Multi-platform connectors (Amazon, Shopify, Etsy, TikTok Shop, eBay).
- `server/inventory.py`: Multi-channel inventory balancing, loop-free fanout, drift reconciliation.
- `server/marketing.py`: SEO blog generator, Reddit lead scout, drip emails.
- `server/reviews_ugc.py`: UGC drips, sentiment classifier, draft replies.
- `server/main.py`: Route endpoints, admin telemetry, quota reservation.
- `frontend/dashboard.html`: Complete dashboard UI sections.
- `frontend/admin.html`: MRR/ARR and growth telemetry dashboard.
- `tests/`: Comprehensive unit, integration, and E2E test suites.
