"""
main.py — FastAPI application entry point.
All routes, startup/shutdown lifecycle, and static file serving.
"""

import os
import uuid
import logging
import hmac
import re
from time import perf_counter
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional
import threading

import bleach
import stripe
from fastapi import (FastAPI, Depends, HTTPException, Request, Header, BackgroundTasks, File, UploadFile, Query)
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.orm import Session

from .database import get_db, init_db, User, APIKey, UsageRecord, BlogPost
from .models import (
    AdminMRRMetricsResponse, BrandPersonaRequest, BrandPersonaResponse, MarketplaceOptimizeRequest,
    MarketplaceOptimizeResponse, AddOnCheckoutRequest, RequestPasswordReset,
    ResetPasswordSubmit, IntegrationSaveRequest, PushRequest, CampaignGenerateRequest,
    CampaignPushRequest, ConnectorDiscoverRequest, CampaignVisionGenerateRequest,
    CompetitorMineRequest, CompetitorMineResponse, CustomAIKeyRequest, CustomAIKeyResponse,
    InventoryItemCreate, InventoryItemResponse, InventoryWebhookPayload, InventorySyncLogResponse,
    PostPurchaseDripRequest, PostPurchaseDripResponse, CustomerReviewSubmitRequest,
    CustomerReviewResponse, PriceMarginItemCreate, PriceMarginItemResponse, ShopifyImportRequest,
    ShopifyImportResponse, ConnectorToggleRequest, ConnectorTestRequest,
    ConnectorCredentialsRequest, VerifyEmailRequest, RequestVerificationRequest, UserRegister,
    UserLogin, TokenResponse, UserProfile, APIKeyCreate, APIKeyResponse, APIKeyCreated,
    GenerateRequest, GenerateResponse, CheckoutRequest, OneTimeGenerationsRequest,
    CheckoutResponse, PartnerPlacementCheckoutRequest, UsageSummary,
    HealthResponse, PublicMetricsSummary
)
from .auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    SESSION_COOKIE_NAME,
    register_user,
    authenticate_user,
    create_access_token,
    create_user_api_key,
    revoke_api_key,
    get_current_user_jwt,
    get_current_user_apikey,
    normalize_email,
)
from .ai_engine import generate_copy
from .billing import create_subscription_checkout, create_one_time_checkout, handle_stripe_webhook, get_total_revenue, PLANS, ONE_TIME_GENERATIONS
from .marketing import generate_seo_post
from .config import ADMIN_SECRET, ENVIRONMENT, PUBLIC_BASE_URL, STRICT_CONFIG, TESTING, env_float, env_int, env_list

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)
APP_VERSION = "2.0.0"
BASE_DIR = Path(__file__).parent.parent
limiter = Limiter(key_func=get_remote_address, enabled=not TESTING)
import sentry_sdk
if os.environ.get("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        traces_sample_rate=env_float("SENTRY_TRACES_SAMPLE_RATE", 0.1),
        profiles_sample_rate=env_float("SENTRY_PROFILES_SAMPLE_RATE", 0.0),
    )

ALLOWED_ORIGINS = env_list("ALLOWED_ORIGINS", ["https://snapcopy-ai.onrender.com"])
ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    ["snapcopy-ai.onrender.com", "localhost", "127.0.0.1", "testserver"],
)
TRUSTED_PROXIES = env_list("TRUSTED_PROXIES", ["127.0.0.1"])
ENABLE_API_DOCS = os.getenv("ENABLE_API_DOCS", "").strip().lower() in {"1", "true", "yes", "on"}
DOCS_URL = "/api/docs" if not STRICT_CONFIG or ENABLE_API_DOCS else None
REDOC_URL = "/api/redoc" if not STRICT_CONFIG or ENABLE_API_DOCS else None
MAX_REQUEST_BYTES = env_int(
    "MAX_REQUEST_BYTES",
    20 * 1024 * 1024,
    minimum=1 * 1024 * 1024,
    maximum=50 * 1024 * 1024,
)


async def _start_scheduler() -> None:
    """Start optional automation jobs and fail closed in strict environments."""

    global scheduler_instance
    try:
        from .scheduler import create_scheduler

        scheduler_instance = create_scheduler()
        scheduler_instance.start()
        logger.info("APScheduler background automations started successfully")
    except Exception:
        if STRICT_CONFIG:
            raise
        logger.exception("APScheduler startup note")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global scheduler_instance
    logger.info("KopyKat starting up (environment=%s)", ENVIRONMENT)
    init_db()
    logger.info("Database initialized")
    await _start_scheduler()
    logger.info("KopyKat v%s is live", APP_VERSION)
    try:
        yield
    finally:
        if scheduler_instance:
            try:
                scheduler_instance.shutdown(wait=False)
            except Exception:
                logger.exception("Scheduler shutdown failed")
            scheduler_instance = None
        logger.info("KopyKat shut down gracefully")


app = FastAPI(
    title="KopyKat",
    description="Instant AI-powered marketing copy. Automated. Always on.",
    version=APP_VERSION,
    docs_url=DOCS_URL,
    redoc_url=REDOC_URL,
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials="*" not in ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type", "X-Admin-Secret", "X-Event-ID"],
)
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=TRUSTED_PROXIES)


_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


@app.middleware("http")
async def reject_oversized_requests(request: Request, call_next):
    """Reject oversized requests before multipart/JSON parsing allocates memory."""

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header"})
        if declared_length < 0 or declared_length > MAX_REQUEST_BYTES:
            return JSONResponse(status_code=413, content={"detail": "Request body exceeds the configured limit"})
    return await call_next(request)


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    """Attach a safe correlation ID and server timing to every response."""

    supplied = request.headers.get("X-Request-ID", "")
    request_id = supplied if _REQUEST_ID_RE.fullmatch(supplied) else uuid.uuid4().hex
    request.state.request_id = request_id
    started = perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = str(round((perf_counter() - started) * 1000, 2))
    if response.status_code >= 500:
        logger.error(
            "Request completed with server error",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
            },
        )
    return response

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.tailwindcss.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://api.stripe.com; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    )
    if STRICT_CONFIG:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith(("/static/", "/api.js", "/sw.js", "/manifest.json")):
        response.headers["Cache-Control"] = "public, max-age=3600"
    else:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    """Return a stable validation shape while retaining the request correlation ID."""

    request_id = getattr(request.state, "request_id", "")
    return JSONResponse(
        status_code=422,
        content={
            "detail": jsonable_encoder(exc.errors()),
            "request_id": request_id,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log unexpected failures server-side without exposing implementation details."""

    request_id = getattr(request.state, "request_id", "")
    logger.exception(
        "Unhandled application error",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        },
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )


_ALLOWED_TAGS = ["p", "h2", "h3", "h4", "ul", "ol", "li", "strong", "em", "b", "i", "a", "br", "blockquote"]
_ALLOWED_ATTRS = {"a": ["href", "title", "rel"]}
def sanitize_html(raw: str) -> str:
    return bleach.clean(raw, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True, strip_comments=True)


def _clean_text(raw: object, max_length: int = 4_000) -> str:
    """Return bounded plain text for data that may be rendered or forwarded."""

    return bleach.clean(str(raw or ""), tags=[], attributes={}, strip=True, strip_comments=True)[:max_length].strip()


def _sanitize_campaign_assets(raw_assets: object) -> dict:
    """Keep AI output bounded and safe before persisting or returning it."""

    if not isinstance(raw_assets, dict):
        return {}

    cleaned: dict = {}
    for key in ("detected_product_name", "detected_description"):
        if key in raw_assets:
            cleaned[key] = _clean_text(raw_assets[key])

    blog = raw_assets.get("blog_post")
    if isinstance(blog, dict):
        cleaned["blog_post"] = {
            "title": _clean_text(blog.get("title"), 255),
            "content": sanitize_html(str(blog.get("content") or ""))[:50_000],
        }

    emails = raw_assets.get("email_drip")
    if isinstance(emails, list):
        cleaned_emails = []
        for email in emails[:20]:
            if not isinstance(email, dict):
                continue
            cleaned_emails.append({
                "step": email.get("step"),
                "day": email.get("day"),
                "goal": _clean_text(email.get("goal"), 500),
                "subject": _clean_text(email.get("subject"), 255),
                "body": sanitize_html(str(email.get("body") or ""))[:20_000],
            })
        cleaned["email_drip"] = cleaned_emails

    social_posts = raw_assets.get("social_posts")
    if isinstance(social_posts, list):
        cleaned["social_posts"] = [_clean_text(post, 2_000) for post in social_posts[:50]]

    return cleaned


def _is_valid_admin_secret(candidate: Optional[str]) -> bool:
    """Compare admin credentials without leaking timing information."""

    configured = ADMIN_SECRET.strip()
    supplied = candidate or ""
    return bool(configured) and hmac.compare_digest(supplied, configured)


scheduler_instance = None

frontend_dir = BASE_DIR / "frontend"
if (frontend_dir / "static").exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir / "static")), name="static")

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def landing_page():
    index = frontend_dir / "index.html"
    return HTMLResponse(index.read_text(encoding="utf-8")) if index.exists() else HTMLResponse("<h1>KopyKat — Loading...</h1>")

@app.head("/", include_in_schema=False)
async def landing_head():
    """Return a lightweight success response for platform HEAD probes."""

    return Response(status_code=200)

@app.get("/manifest.json", include_in_schema=False)
async def get_manifest():
    return FileResponse(frontend_dir / "manifest.json")

@app.get("/api.js", include_in_schema=False)
async def get_api_js():
    js_path = frontend_dir / "static" / "api.js"
    if not js_path.exists():
        js_path = frontend_dir / "api.js"
    return FileResponse(js_path, media_type="application/javascript")

@app.get("/sw.js", include_in_schema=False)
async def get_sw():
    return FileResponse(frontend_dir / "sw.js")

@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_page():
    dash = frontend_dir / "dashboard.html"
    return HTMLResponse(dash.read_text(encoding="utf-8")) if dash.exists() else HTMLResponse("<h1>Dashboard — Loading...</h1>")

@app.post("/admin/trigger-seo", include_in_schema=False)
@limiter.limit("10/minute")
async def trigger_seo(request: Request, background_tasks: BackgroundTasks, x_admin_secret: Optional[str] = Header(None, alias="x-admin-secret")):
    if not _is_valid_admin_secret(x_admin_secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    background_tasks.add_task(generate_seo_post)
    return {"status": "ok", "message": "SEO blog generation started in background."}

@app.get("/blog", response_class=HTMLResponse, include_in_schema=False)
async def blog_index(db: Session = Depends(get_db)):
    posts = db.query(BlogPost).filter(BlogPost.published == True).order_by(BlogPost.created_at.desc()).all()
    template_path = frontend_dir / "blog.html"
    if not template_path.exists():
        return HTMLResponse("<h1>Blog setup pending...</h1>")
    template = template_path.read_text(encoding="utf-8")
    items = "".join(f'<div class="card"><div>{p.created_at.strftime("%B %d, %Y")}</div><h2><a href="/blog/{p.slug}">{bleach.clean(p.title)}</a></h2><p>{bleach.clean(p.meta_desc or "")}</p></div>' for p in posts)
    return HTMLResponse(template.replace("<!-- POSTS -->", items or "<p>No posts yet. The AI is writing the first one!</p>"))

@app.get("/blog/{slug}", response_class=HTMLResponse, include_in_schema=False)
async def blog_post(slug: str, db: Session = Depends(get_db)):
    post = db.query(BlogPost).filter(BlogPost.slug == slug, BlogPost.published == True).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    path = frontend_dir / "post.html"
    if not path.exists():
        return HTMLResponse("<h1>Post layout pending...</h1>")
    html = path.read_text(encoding="utf-8").replace("{{title}}", bleach.clean(post.title)).replace("{{content}}", sanitize_html(post.content)).replace("{{meta_desc}}", bleach.clean(post.meta_desc or "")).replace("{{date}}", post.created_at.strftime("%B %d, %Y"))
    return HTMLResponse(html)

@app.get("/robots.txt", response_class=HTMLResponse, include_in_schema=False)
async def get_robots_txt():
    robots = f"""User-agent: *
Allow: /
Allow: /blog
Allow: /blog/

Sitemap: {PUBLIC_BASE_URL}/sitemap.xml
"""
    return HTMLResponse(robots, media_type="text/plain")

@app.get("/sitemap.xml", response_class=HTMLResponse, include_in_schema=False)
async def get_sitemap_xml(db: Session = Depends(get_db)):
    base = PUBLIC_BASE_URL
    posts = db.query(BlogPost).filter(BlogPost.published == True).order_by(BlogPost.created_at.desc()).all()
    
    xml_entries = [
        f"""  <url>
    <loc>{base}/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>""",
        f"""  <url>
    <loc>{base}/blog</loc>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>"""
    ]
    
    for p in posts:
        mod_date = p.created_at.strftime("%Y-%m-%d")
        xml_entries.append(f"""  <url>
    <loc>{base}/blog/{p.slug}</loc>
    <lastmod>{mod_date}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.7</priority>
  </url>""")
    
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(xml_entries)}
</urlset>"""
    return HTMLResponse(xml_content, media_type="application/xml")

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    return HealthResponse(status="ok", version=APP_VERSION, timestamp=datetime.utcnow())

@app.head("/health", include_in_schema=False)
async def health_head():
    return Response(status_code=200)


@app.get("/ready", response_model=HealthResponse, tags=["System"])
async def readiness_check(db: Session = Depends(get_db)):
    """Readiness probe that confirms the configured database is reachable."""

    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Readiness check failed", extra={"request_id": None})
        raise HTTPException(status_code=503, detail="Service is not ready") from None
    return HealthResponse(status="ready", version=APP_VERSION, timestamp=datetime.utcnow())

@app.head("/ready", include_in_schema=False)
async def readiness_head():
    return Response(status_code=200)

@app.get("/api/plans", tags=["Billing"])
async def list_plans():
    return {
        "subscriptions": {k: {"name": v["name"], "price_usd": v["price_usd"], "monthly_generations": v["monthly_generations"], "features": v["features"]} for k, v in PLANS.items()},
        "one_time_generations": {k: {"name": v["name"], "price_usd": v["price_usd"], "generations": v["generations"]} for k, v in ONE_TIME_GENERATIONS.items()}
    }


def _calculate_mrr_metrics(db: Session) -> dict:
    """Calculate recurring revenue from persisted billing state only.

    Stripe subscription rows are the source of truth when present. The user
    plan is used only as a compatibility fallback for legacy records that
    predate subscription persistence. Active users are counted once even if a
    webhook replay or historical migration left duplicate active rows.
    """

    from .database import Subscription, RevenueRecord
    from sqlalchemy import func

    tier_names = ("boutique", "standard", "megastore")
    tier_prices = {name: float(PLANS[name]["price_usd"]) for name in tier_names}
    tier_counts = {name: 0 for name in tier_names}

    active_user_ids: set[str] = set()
    for subscription in db.query(Subscription).filter(
        Subscription.status == "active",
        Subscription.plan.in_(tier_names),
    ).all():
        if subscription.user_id in active_user_ids:
            continue
        active_user_ids.add(subscription.user_id)
        tier_counts[subscription.plan] += 1

    canceled_user_ids = {
        subscription.user_id
        for subscription in db.query(Subscription).filter(
            Subscription.status == "canceled",
            Subscription.plan.in_(tier_names),
        ).all()
    }
    past_due_user_ids = {
        subscription.user_id
        for subscription in db.query(Subscription).filter(
            Subscription.status == "past_due",
            Subscription.plan.in_(tier_names),
        ).all()
    }

    # Legacy users may have a paid plan without a Subscription row. Do not
    # infer active revenue for users who are disabled or already represented by
    # any subscription state.
    represented_user_ids = {
        subscription.user_id
        for subscription in db.query(Subscription).filter(
            Subscription.plan.in_(tier_names),
        ).all()
    }
    for user in db.query(User).filter(
        User.plan.in_(tier_names),
        User.is_active == True,
    ).all():
        if user.id in represented_user_ids or user.id in active_user_ids:
            continue
        active_user_ids.add(user.id)
        tier_counts[user.plan] += 1

    mrr_usd = round(sum(tier_counts[name] * tier_prices[name] for name in tier_names), 2)
    total_rev_cents = db.query(func.sum(RevenueRecord.amount_cents)).filter(
        RevenueRecord.status == "succeeded",
        func.lower(func.coalesce(RevenueRecord.currency, "usd")) == "usd",
    ).scalar() or 0
    total_lifetime_revenue_usd = round(total_rev_cents / 100.0, 2)

    subscription_base = len(active_user_ids | canceled_user_ids)
    churn_rate_pct = round((len(canceled_user_ids) / subscription_base * 100.0), 2) if subscription_base else 0.0
    if mrr_usd:
        annual_run_rate = mrr_usd * 12.0
        valuation = {
            "asset_sale_range": f"${annual_run_rate * 3:,.0f} - ${annual_run_rate * 5:,.0f}",
            "arr_multiple_range": "3x - 5x ARR",
        }
    else:
        valuation = {
            "asset_sale_range": "Not available until recurring revenue exists",
            "arr_multiple_range": "Not available",
        }

    return {
        "mrr_usd": mrr_usd,
        "arr_usd": round(mrr_usd * 12.0, 2),
        "active_subscribers": len(active_user_ids),
        "canceled_subscribers": len(canceled_user_ids),
        "past_due_subscribers": len(past_due_user_ids),
        "churn_rate_pct": churn_rate_pct,
        "active_subscribers_by_tier": tier_counts,
        "total_lifetime_revenue_usd": total_lifetime_revenue_usd,
        "total_registered_merchants": db.query(User).count(),
        "pricing_model": {f"{name}_usd_mo": tier_prices[name] for name in tier_names},
        "software_asset_score": None,
        "valuation_estimate_usd": valuation,
    }


@app.get("/api/metrics/summary", tags=["System"], response_model=PublicMetricsSummary)
async def public_metrics_summary(db: Session = Depends(get_db)):
    from .database import Campaign
    from .integrations import CONNECTOR_REGISTRY
    from sqlalchemy import func

    total_campaigns = db.query(func.count(Campaign.id)).scalar() or 0
    mrr_metrics = _calculate_mrr_metrics(db)
    supported_marketplaces = len({connector.platform_name for connector in CONNECTOR_REGISTRY.values()})
    return PublicMetricsSummary(
        total_campaigns_generated=total_campaigns,
        supported_marketplaces_count=supported_marketplaces,
        active_subscribers_mrr_usd=mrr_metrics["mrr_usd"],
        estimated_seller_hours_saved=int(total_campaigns * 1.5),
        platform_uptime_pct=None,
        api_version=APP_VERSION
    )

@app.post("/auth/request-verification", tags=["Auth"])
@limiter.limit("5/minute")
async def request_verification(request: Request, body: RequestVerificationRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    from .database import VerificationToken
    import secrets
    import hashlib
    from datetime import timedelta
    
    user = db.query(User).filter(User.email == normalize_email(body.email)).first()
    if not user:
        return {"message": "If this email is registered, a verification link has been sent."}
    
    token_str = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token_str.encode()).hexdigest()
    
    db.query(VerificationToken).filter(
        VerificationToken.user_id == user.id,
        VerificationToken.token_type == "email_verification",
    ).delete(synchronize_session=False)
    vt = VerificationToken(
        token=token_hash,
        user_id=user.id,
        token_type="email_verification",
        expires_at=datetime.utcnow() + timedelta(hours=24)
    )
    db.add(vt)
    db.commit()
    
    from .scheduler import _send_email
    background_tasks.add_task(
        _send_email,
        "Verify your KopyKat email",
        f"Click the link below to verify your email address:<br><a href='{PUBLIC_BASE_URL}/verify?token={token_str}'>Verify Email</a>",
        user.email
    )
    return {"message": "If this email is registered, a verification link has been sent."}

@app.post("/auth/verify-email", tags=["Auth"])
@limiter.limit("10/minute")
async def verify_email(request: Request, body: VerifyEmailRequest, db: Session = Depends(get_db)):
    from .database import VerificationToken
    import hashlib
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    
    vt = db.query(VerificationToken).filter(
        VerificationToken.token == token_hash,
        VerificationToken.token_type == "email_verification"
    ).first()
    
    if not vt or vt.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired verification token.")
    
    user = db.query(User).filter(User.id == vt.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    
    user.is_verified = True
    db.delete(vt)
    db.commit()
    return {"status": "success", "message": "Email verified successfully."}

@app.post("/auth/request-password-reset", tags=["Auth"])
@limiter.limit("5/minute")
async def request_password_reset(request: Request, body: RequestPasswordReset, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    from .database import VerificationToken
    import secrets
    import hashlib
    from datetime import timedelta
    
    user = db.query(User).filter(User.email == normalize_email(body.email)).first()
    if not user:
        return {"message": "If this email is registered, a password reset link has been sent."}
    
    token_str = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token_str.encode()).hexdigest()
    
    db.query(VerificationToken).filter(
        VerificationToken.user_id == user.id,
        VerificationToken.token_type == "password_reset",
    ).delete(synchronize_session=False)
    vt = VerificationToken(
        token=token_hash,
        user_id=user.id,
        token_type="password_reset",
        expires_at=datetime.utcnow() + timedelta(hours=2)
    )
    db.add(vt)
    db.commit()
    
    from .scheduler import _send_email
    background_tasks.add_task(
        _send_email,
        "Reset your KopyKat password",
        f"Click the link below to reset your password:<br><a href='{PUBLIC_BASE_URL}/reset-password?token={token_str}'>Reset Password</a>",
        user.email
    )
    return {"message": "If this email is registered, a password reset link has been sent."}

@app.post("/auth/reset-password", tags=["Auth"])
@limiter.limit("10/minute")
async def reset_password(request: Request, body: ResetPasswordSubmit, db: Session = Depends(get_db)):
    from .database import VerificationToken
    from .auth import hash_password
    import hashlib
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    
    vt = db.query(VerificationToken).filter(
        VerificationToken.token == token_hash,
        VerificationToken.token_type == "password_reset"
    ).first()
    
    if not vt or vt.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset token.")
    
    user = db.query(User).filter(User.id == vt.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    
    user.hashed_password = hash_password(body.new_password)
    user.auth_version = (user.auth_version or 1) + 1
    # A password reset is a credential-recovery event; previously issued API
    # keys are revoked so a compromised credential cannot survive the reset.
    db.query(APIKey).filter(APIKey.user_id == user.id, APIKey.is_active == True).update({"is_active": False})
    db.delete(vt)
    db.commit()
    return {"status": "success", "message": "Password reset successfully. You can now log in."}

@app.post("/auth/register", response_model=TokenResponse, tags=["Auth"])
@limiter.limit("5/minute")
async def register(request: Request, response: Response, body: UserRegister, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    user = register_user(body.email, body.password, body.full_name, db)
    from .scheduler import _send_email
    background_tasks.add_task(_send_email, "Welcome to KopyKat", f"Hi {body.full_name or 'there'},<br><br>Welcome to KopyKat! Your account is loaded with 5 free generations.", user.email)
    token = create_access_token(user.id, user.email, user.auth_version)
    _set_session_cookie(response, token)
    return TokenResponse(access_token=token, plan=user.plan, generations=user.generations)

@app.post("/auth/login", response_model=TokenResponse, tags=["Auth"])
@limiter.limit("10/minute")
async def login(request: Request, response: Response, body: UserLogin, db: Session = Depends(get_db)):
    user = authenticate_user(body.email, body.password, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user.id, user.email, user.auth_version)
    _set_session_cookie(response, token)
    return TokenResponse(access_token=token, plan=user.plan, generations=user.generations)


def _set_session_cookie(response: Response, token: str) -> None:
    """Issue a browser session cookie without changing the API token contract."""

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=STRICT_CONFIG,
        samesite="lax",
        path="/",
    )


@app.post("/auth/logout", tags=["Auth"])
@limiter.limit("20/minute")
async def logout(request: Request, response: Response):
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return {"status": "logged_out"}

@app.get("/auth/me", response_model=UserProfile, tags=["Auth"])
async def get_profile(current_user: User = Depends(get_current_user_jwt)):
    return current_user

@app.post("/api/keys", response_model=APIKeyCreated, tags=["API Keys"])
async def create_api_key(body: APIKeyCreate, current_user: User = Depends(get_current_user_jwt), db: Session = Depends(get_db)):
    raw, api = create_user_api_key(current_user, body.name, db)
    return APIKeyCreated(id=api.id, key_prefix=api.key_prefix, name=api.name, is_active=api.is_active, last_used=api.last_used, requests_today=api.requests_today, created_at=api.created_at, raw_key=raw)

@app.get("/api/keys", response_model=list[APIKeyResponse], tags=["API Keys"])
async def list_api_keys(current_user: User = Depends(get_current_user_jwt), db: Session = Depends(get_db)):
    return db.query(APIKey).filter(APIKey.user_id == current_user.id, APIKey.is_active == True).all()

@app.delete("/api/keys/{key_id}", tags=["API Keys"])
async def delete_api_key(key_id: str, current_user: User = Depends(get_current_user_jwt), db: Session = Depends(get_db)):
    if not revoke_api_key(key_id, current_user, db):
        raise HTTPException(status_code=404, detail="Key not found")
    return {"status": "revoked"}

_quota_lock = threading.RLock()

def reserve_user_generations(user_id: str, cost: int, db: Session) -> tuple[int, int]:
    """
    Atomically reserves generations from user's balance with row locking where supported.
    Prioritizes monthly bucket before purchased bucket.
    Returns (monthly_used, purchased_used).
    """
    with _quota_lock:
        query = db.query(User).filter(User.id == user_id)
        if getattr(db.bind, "dialect", None) and db.bind.dialect.name != "sqlite":
            query = query.with_for_update()
        db_user = query.first()
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")

        # Reconcile bucket state if total was altered directly
        current_total = (db_user.monthly_generations or 0) + (db_user.purchased_generations or 0)
        if db_user.generations != current_total:
            if db_user.generations > (db_user.purchased_generations or 0):
                db_user.monthly_generations = db_user.generations - (db_user.purchased_generations or 0)
            else:
                db_user.monthly_generations = 0
                db_user.purchased_generations = db_user.generations

        monthly_avail = db_user.monthly_generations or 0
        purchased_avail = db_user.purchased_generations or 0
        total_avail = monthly_avail + purchased_avail

        if total_avail < cost:
            raise HTTPException(status_code=402, detail="Insufficient campaigns or generation credits remaining. Please upgrade your plan.")

        monthly_used = min(monthly_avail, cost)
        purchased_used = cost - monthly_used

        db_user.monthly_generations = monthly_avail - monthly_used
        db_user.purchased_generations = purchased_avail - purchased_used
        db_user.generations = db_user.monthly_generations + db_user.purchased_generations
        db.commit()
        return monthly_used, purchased_used

def refund_user_generations(user_id: str, monthly_refund: int, purchased_refund: int, db: Session):
    """Atomically restores previously reserved generations to the user's balance."""
    with _quota_lock:
        db_user = db.query(User).filter(User.id == user_id).first()
        if db_user:
            db_user.monthly_generations = (db_user.monthly_generations or 0) + monthly_refund
            db_user.purchased_generations = (db_user.purchased_generations or 0) + purchased_refund
            db_user.generations = db_user.monthly_generations + db_user.purchased_generations
            db.commit()

@app.post("/api/generate", response_model=GenerateResponse, tags=["Generate"])
@limiter.limit("60/minute")
async def generate(request: Request, body: GenerateRequest, auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    user, api_key = auth
    cost = body.variations

    monthly_used, purchased_used = reserve_user_generations(user.id, cost, db)

    try:
        result = await generate_copy(
            copy_type=body.type,
            context=body.context,
            tone=body.tone or "professional",
            variations=body.variations,
            max_tokens=body.max_words,
            user_id=user.id,
            db=db
        )
    except Exception:
        refund_user_generations(user.id, monthly_used, purchased_used, db)
        raise HTTPException(status_code=500, detail="AI generation failed. Your credits have been refunded.")

    actual = result.get("generations_used", body.variations) if isinstance(result, dict) else body.variations
    if actual < cost:
        refund = cost - actual
        refund_purchased = min(purchased_used, refund)
        refund_monthly = refund - refund_purchased
        refund_user_generations(user.id, refund_monthly, refund_purchased, db)

    db_user = db.query(User).filter(User.id == user.id).first()
    vars_list = result.get("variations") if isinstance(result, dict) else None
    if vars_list is None:
        if isinstance(result, dict) and "output" in result:
            vars_list = [result["output"]]
        else:
            vars_list = []
    gen_time = result.get("generation_time_ms", 0) if isinstance(result, dict) else 0

    first_output = vars_list[0] if vars_list else ""
    return GenerateResponse(
        type=body.type,
        variations=vars_list,
        output=first_output,
        generations_used=actual,
        generations=db_user.generations if db_user else 0,
        generation_time_ms=gen_time
    )

@app.post("/billing/subscribe", response_model=CheckoutResponse, tags=["Billing"])
async def subscribe(body: CheckoutRequest, current_user: User = Depends(get_current_user_jwt), db: Session = Depends(get_db)):
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Payment gateway unavailable. Stripe is not configured.")
    return CheckoutResponse(**create_subscription_checkout(plan=body.plan, user=current_user, db=db))

@app.post("/billing/checkout", response_model=CheckoutResponse, tags=["Billing"])
async def checkout(body: CheckoutRequest, current_user: User = Depends(get_current_user_jwt), db: Session = Depends(get_db)):
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Payment gateway unavailable. Stripe is not configured.")
    return CheckoutResponse(**create_subscription_checkout(plan=body.plan, user=current_user, db=db))

@app.post("/billing/one-time", response_model=CheckoutResponse, tags=["Billing"])
async def buy_one_time(body: OneTimeGenerationsRequest, current_user: User = Depends(get_current_user_jwt), db: Session = Depends(get_db)):
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Payment gateway unavailable. Stripe is not configured.")
    return CheckoutResponse(**create_one_time_checkout(pack=body.tier, user=current_user, db=db))

@app.post("/billing/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, stripe_signature: Optional[str] = Header(None, alias="stripe-signature"), db: Session = Depends(get_db)):
    return JSONResponse(content=handle_stripe_webhook(await request.body(), stripe_signature or "", db))

@app.get("/billing/status", tags=["Billing"])
async def billing_status(current_user: User = Depends(get_current_user_jwt), db: Session = Depends(get_db)):
    from .database import Subscription
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id, Subscription.status == "active").order_by(Subscription.created_at.desc()).first()
    return {
        "plan": current_user.plan,
        "status": sub.status if sub else "free",
        "generations": current_user.generations,
        "monthly_limit": current_user.monthly_limit,
        "current_period_end": sub.current_period_end if sub else None
    }

@app.get("/api/usage", response_model=UsageSummary, tags=["Usage"])
async def get_usage(current_user: User = Depends(get_current_user_jwt), db: Session = Depends(get_db)):
    from sqlalchemy import func
    from .database import Subscription
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id, Subscription.status == "active").order_by(Subscription.created_at.desc()).first()
    agg = db.query(func.count(UsageRecord.id).label("total_requests"), func.sum(UsageRecord.generations_used).label("total_generations")).filter(UsageRecord.user_id == current_user.id).first()
    return UsageSummary(
        total_requests=agg.total_requests or 0,
        total_generations_used=agg.total_generations or 0,
        generations=current_user.generations,
        monthly_limit=current_user.monthly_limit,
        plan=current_user.plan,
        period_start=sub.current_period_start.isoformat() if sub and sub.current_period_start else None,
        period_end=sub.current_period_end.isoformat() if sub and sub.current_period_end else None
    )

@app.get("/admin/revenue", tags=["Admin"])
@limiter.limit("20/minute")
async def admin_revenue(request: Request, x_admin_secret: Optional[str] = Header(None, alias="x-admin-secret"), db: Session = Depends(get_db)):
    if not _is_valid_admin_secret(x_admin_secret):
        raise HTTPException(status_code=403, detail="Forbidden")
    return get_total_revenue(db)

@app.get("/admin/mrr-metrics", tags=["Admin"], response_model=AdminMRRMetricsResponse)
@limiter.limit("20/minute")
async def admin_mrr_metrics(request: Request, x_admin_secret: Optional[str] = Header(None, alias="x-admin-secret"), db: Session = Depends(get_db)):
    if not _is_valid_admin_secret(x_admin_secret):
        raise HTTPException(status_code=403, detail="Forbidden")

    return _calculate_mrr_metrics(db)

@app.get("/api/admin/stats", tags=["Admin"])
@limiter.limit("20/minute")
async def admin_stats(request: Request, x_admin_secret: Optional[str] = Header(None, alias="x-admin-secret"), db: Session = Depends(get_db)):
    if not _is_valid_admin_secret(x_admin_secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    from sqlalchemy import func
    from .database import RevenueRecord
    users = db.query(User).count()
    paying = db.query(User).filter(
        User.is_active == True,
        User.plan.in_(["boutique", "standard", "megastore"]),
    ).count()
    revenue = db.query(func.sum(RevenueRecord.amount_cents)).filter(
        RevenueRecord.status == "succeeded",
        func.lower(func.coalesce(RevenueRecord.currency, "usd")) == "usd",
    ).scalar() or 0
    reqs = db.query(func.count(UsageRecord.id)).scalar() or 0
    gens = db.query(func.sum(UsageRecord.generations_used)).scalar() or 0
    recent = db.query(User).order_by(User.created_at.desc()).limit(10).all()
    return {
        "total_users": users,
        "paying_users": paying,
        "total_revenue_cents": revenue,
        "total_requests": reqs,
        "total_generations": gens,
        "recent_users": [{"email": u.email, "plan": u.plan, "created_at": u.created_at.isoformat()} for u in recent]
    }

@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_page():
    path = BASE_DIR / "frontend" / "admin.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Admin panel not found")
    return HTMLResponse(
        path.read_text(encoding="utf-8"),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )

# Integration/campaign routes
@app.post("/api/integrations", tags=["Integrations"])
async def save_integration(request: Request, body: IntegrationSaveRequest, auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .database import UserIntegration
    from .auth import encrypt_credentials
    import json
    import uuid
    user, _ = auth
    existing = db.query(UserIntegration).filter(UserIntegration.user_id == user.id, UserIntegration.platform == body.platform).first()
    enc = encrypt_credentials(json.dumps(body.credentials))
    if existing:
        existing.credentials = enc
        existing.status = "connected"
    else:
        db.add(UserIntegration(id=str(uuid.uuid4()), user_id=user.id, platform=body.platform, credentials=enc, status="connected"))
    db.commit()
    return {"message": f"{body.platform.capitalize()} integration saved"}

@app.get("/api/integrations", tags=["Integrations"])
async def get_integrations(auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .database import UserIntegration
    from .auth import decrypt_credentials
    from .integrations import fetch_metadata
    import json
    user, _ = auth
    ints = db.query(UserIntegration).filter(UserIntegration.user_id == user.id).all()
    connected = []
    metadata = {}
    for i in ints:
        connected.append(i.platform)
        try:
            opts = fetch_metadata(i.platform, json.loads(decrypt_credentials(i.credentials)))
            if opts:
                metadata[i.platform] = opts
        except Exception:
            pass
    return {"connected": connected, "metadata": metadata}

@app.post("/api/push", tags=["Integrations"])
async def push_content(request: Request, body: PushRequest, background_tasks: BackgroundTasks, auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .database import UserIntegration, PushJob
    from .auth import decrypt_credentials
    import json
    import uuid
    user, _ = auth
    integration = db.query(UserIntegration).filter(UserIntegration.user_id == user.id, UserIntegration.platform == body.platform).first()
    if not integration:
        raise HTTPException(status_code=400, detail=f"No {body.platform} integration configured.")
    try:
        creds = json.loads(decrypt_credentials(integration.credentials))
    except Exception:
        integration.status = "invalid_credentials"
        db.commit()
        raise HTTPException(status_code=400, detail="Integration credentials invalid or corrupted. Please reconnect.")
    safe_content = sanitize_html(body.content)
    if not safe_content.strip():
        raise HTTPException(status_code=400, detail="Content contains no supported text or markup.")
    safe_title = _clean_text(body.title or "Generated via KopyKat", 255) or "Generated via KopyKat"
    job_id = str(uuid.uuid4())
    db.add(PushJob(id=job_id, user_id=user.id, platform=body.platform, status="pending"))
    db.commit()
    from .integrations import background_push
    background_tasks.add_task(background_push, body.platform, creds, safe_title, safe_content, body.metadata, integration.id, job_id)
    return JSONResponse(status_code=202, content={"message": "Push accepted", "job_id": job_id})

@app.get("/api/push/status/{job_id}", tags=["Integrations"])
async def get_push_status(job_id: str, auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .database import PushJob
    user, _ = auth
    job = db.query(PushJob).filter(PushJob.id == job_id, PushJob.user_id == user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Push job not found.")
    return {"status": job.status, "details": job.details}

@app.post("/api/public/demo", tags=["Public"])
@limiter.limit("2/day")
async def api_public_demo(request: Request, body: CampaignGenerateRequest, db: Session = Depends(get_db)):
    from .campaigns import generate_demo_campaign
    try:
        return {"assets": _sanitize_campaign_assets(generate_demo_campaign(body.keyword, body.product_desc))}
    except Exception as e:
        logger.error("Public demo failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Demo generation failed due to an internal error.")

# ---------------------------------------------------------------------------
# Dropship Partners — paid directory + private activation + merchant connector
# ---------------------------------------------------------------------------

@app.get("/dropship-partners", response_class=HTMLResponse, include_in_schema=False)
async def dropship_partners_page():
    """Serve the public paid-placement directory page."""
    page = BASE_DIR / "frontend" / "dropship-partners.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="Page not found.")
    return FileResponse(page)


@app.get("/dropship-partners/activate", response_class=HTMLResponse, include_in_schema=False)
async def dropship_partner_activation_page():
    """Serve the private partner activation page without caching its token."""

    page = BASE_DIR / "frontend" / "partner-activation.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="Page not found.")
    return FileResponse(
        page,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Robots-Tag": "noindex, nofollow, noarchive",
        },
    )


@app.get("/api/dropship-partners", tags=["Dropship Partners"])
@limiter.limit("60/minute")
async def api_dropship_partners_list(request: Request, db: Session = Depends(get_db)):
    """Return only active paid placements; private contact data is never included."""
    from .dropship_billing import active_partner_records

    return {
        "disclaimer": (
            "All listings are paid advertising placements. KopyKat does not endorse "
            "or certify any listed vendor. API availability is not guaranteed."
        ),
        "partners": active_partner_records(db),
    }


@app.get("/api/dropship-partners/featured", tags=["Dropship Partners"])
@limiter.limit("60/minute")
async def api_featured_dropship_partners(request: Request, db: Session = Depends(get_db)):
    """Return active featured front-page placements in slot order."""

    from .dropship_billing import active_partner_records

    return {"partners": active_partner_records(db, placement_type="featured")[:5]}


@app.get("/api/dropship-partners/activation", tags=["Dropship Partners"])
@limiter.limit("20/minute")
async def api_dropship_partner_activation_status(
    request: Request,
    token: str = Query(..., min_length=32, max_length=128),
    db: Session = Depends(get_db),
):
    """Return private activation status for a holder of a valid invite token."""

    from .dropship_billing import activation_status

    return activation_status(token, db)


@app.post("/api/dropship-partners/activation/checkout", tags=["Dropship Partners"])
@limiter.limit("5/minute")
async def api_dropship_partner_activation_checkout(
    request: Request,
    body: PartnerPlacementCheckoutRequest,
    db: Session = Depends(get_db),
):
    """Create a fixed-price Stripe subscription checkout for a partner invite."""

    from .dropship_billing import create_partner_checkout

    return create_partner_checkout(
        token=body.token,
        placement_type=body.placement_type,
        slot=body.slot,
        interval=body.interval,
        logo_url=body.logo_url,
        service_url=body.service_url,
        db=db,
    )


@app.post("/admin/dropship-partners/invitations", tags=["Admin"])
@limiter.limit("10/hour")
async def admin_send_dropship_partner_invitations(
    request: Request,
    partner_key: Optional[str] = Query(None, max_length=50),
    x_admin_secret: Optional[str] = Header(None, alias="x-admin-secret"),
    db: Session = Depends(get_db),
):
    """Manually trigger the same per-partner invitation job used by the scheduler."""

    if not _is_valid_admin_secret(x_admin_secret):
        raise HTTPException(status_code=403, detail="Forbidden")
    from .dropship_billing import send_configured_partner_invites

    return {"results": send_configured_partner_invites(db, partner_key=partner_key)}


@app.post("/api/dropship-partners/{partner_key}/connect", tags=["Dropship Partners"])
@limiter.limit("10/minute")
async def api_dropship_partner_connect(
    request: Request,
    partner_key: str,
    auth: tuple = Depends(get_current_user_apikey),
    db: Session = Depends(get_db),
):
    """
    Pre-load an active paid partner's verified connector spec into the user's
    account. Creates a draft CustomConnector record. Idempotent — returns the
    existing record if a connector for this partner already exists. Requires auth.
    """
    from .dropship_connectors import PARTNERS, CONNECTOR_SPECS
    from .dropship_billing import active_partner_keys
    from .connector_registry import validate_connector_spec, ConnectorError
    from .database import CustomConnector

    user, _ = auth

    if partner_key not in PARTNERS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown partner key '{partner_key}'. "
                   f"Valid keys: {', '.join(PARTNERS.keys())}",
        )

    if partner_key not in active_partner_keys(db):
        raise HTTPException(
            status_code=403,
            detail="This partner placement is not currently active.",
        )

    partner_meta = PARTNERS[partner_key]
    spec = CONNECTOR_SPECS[partner_key]

    existing = (
        db.query(CustomConnector)
        .filter(
            CustomConnector.user_id == user.id,
            CustomConnector.platform_name == partner_meta["name"],
        )
        .first()
    )
    if existing:
        return {
            "status": "existing",
            "connector_id": existing.id,
            "platform_name": existing.platform_name,
            "message": (
                f"A connector for {partner_meta['name']} already exists in your account. "
                "Add your API credentials in the dashboard to activate it."
            ),
        }

    try:
        validated_spec = validate_connector_spec(spec)
    except ConnectorError as exc:
        logger.error("Dropship connector spec validation failed for %s: %s", partner_key, exc)
        raise HTTPException(status_code=500, detail="Partner connector spec is invalid.")

    connector_id = str(uuid.uuid4())
    import json as _json
    new_connector = CustomConnector(
        id=connector_id,
        user_id=user.id,
        platform_name=validated_spec["platform_name"],
        source_url=partner_meta["docs_url"],
        base_url=validated_spec["base_url"],
        spec=_json.dumps(validated_spec),
        authentication_modes=str((validated_spec.get("auth") or {}).get("type") or "unknown"),
        operation_count=len(validated_spec.get("operations") or []),
        status="draft",
    )
    db.add(new_connector)
    db.commit()
    db.refresh(new_connector)

    logger.info(
        "Dropship partner connector created: user=%s partner=%s connector=%s",
        user.id, partner_key, connector_id,
    )

    return {
        "status": "created",
        "connector_id": connector_id,
        "platform_name": partner_meta["name"],
        "docs_url": partner_meta["docs_url"],
        "auth_type": partner_meta["auth_type"],
        "message": (
            f"{partner_meta['name']} connector added as a draft. "
            "Go to Dashboard → Connectors to enter your API credentials and activate it."
        ),
    }


@app.post("/api/connector/discover", tags=["Connectors"])
@limiter.limit("5/minute")
async def api_connector_discover(
    request: Request,
    body: ConnectorDiscoverRequest,
    auth: tuple = Depends(get_current_user_apikey),
    db: Session = Depends(get_db)
):
    from .connector_engine import discover_connector, ConnectorError
    from .database import CustomConnector
    import uuid
    import json
    
    user, _ = auth
    
    try:
        spec = discover_connector(body.url)
    except ConnectorError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="An error occurred during discovery.")
        
    connector_id = str(uuid.uuid4())
    ops_count = len(spec.get("operations", []))
    auth_modes = spec.get("authentication_modes", [])
    
    new_connector = CustomConnector(
        id=connector_id,
        user_id=user.id,
        platform_name=spec.get("platform_name", "Unknown Platform"),
        source_url=spec.get("source_url", body.url),
        base_url=spec.get("base_url", ""),
        spec=json.dumps(spec),
        authentication_modes=",".join(auth_modes),
        operation_count=ops_count,
        status="draft"
    )
    db.add(new_connector)
    db.commit()
    
    return {
        "id": connector_id,
        "platform_name": new_connector.platform_name,
        "base_url": new_connector.base_url,
        "operation_count": ops_count,
        "authentication_modes": auth_modes,
        "status": "draft"
    }

@app.post("/api/catalog/parse-csv", tags=["Campaigns"])
async def api_parse_csv(request: Request, file: UploadFile = File(...), auth: tuple = Depends(get_current_user_apikey)):
    import csv
    import io
    from .ai_engine import analyze_csv_mapping
    max_upload_bytes = 5 * 1024 * 1024
    content = await file.read(max_upload_bytes + 1)
    if len(content) > max_upload_bytes:
        raise HTTPException(status_code=413, detail="CSV file exceeds the 5 MB upload limit.")
    try:
        text_content = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded.")
    rows = list(csv.reader(io.StringIO(text_content)))
    if len(rows) < 2:
        raise HTTPException(status_code=400, detail="CSV is empty or missing headers.")
    if len(rows) > 5_001 or len(rows[0]) > 100:
        raise HTTPException(status_code=413, detail="CSV exceeds the supported row or column limit.")
    headers = rows[0]
    mapping = await analyze_csv_mapping(headers, rows[1])
    name_col = mapping.get("name_col", "")
    desc_col = mapping.get("desc_col", "")
    if not name_col:
        raise HTTPException(status_code=400, detail="AI could not identify a Product Name column.")
    try:
        name_idx = headers.index(name_col)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"AI returned invalid name column: {name_col}")
    desc_idx = headers.index(desc_col) if desc_col in headers else -1
    results = []
    for r in rows[1:]:
        if len(r) <= name_idx or not r[name_idx].strip():
            continue
        results.append({"name": r[name_idx], "desc": r[desc_idx] if desc_idx != -1 and len(r) > desc_idx else ""})
    return {"items": results[:100], "mapping_used": mapping}

@app.post("/api/campaign/generate", tags=["Campaigns"])
@limiter.limit("5/minute")
async def api_campaign_generate(request: Request, body: CampaignGenerateRequest, auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .database import Campaign
    from .campaigns import generate_omni_campaign
    import uuid
    import json
    user, _ = auth

    monthly_used, purchased_used = reserve_user_generations(user.id, 1, db)

    try:
        data = _sanitize_campaign_assets(generate_omni_campaign(body.keyword, body.product_desc))
        cid = str(uuid.uuid4())
        name = f"Campaign: {body.keyword.title()}"
        db.add(Campaign(id=cid, user_id=user.id, name=name, assets=json.dumps(data)))
        db.commit()
        return {"id": cid, "name": name, "assets": data}
    except ValueError as e:
        refund_user_generations(user.id, monthly_used, purchased_used, db)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        refund_user_generations(user.id, monthly_used, purchased_used, db)
        raise HTTPException(status_code=500, detail="Generation failed due to an internal error. Your balance was not charged.")

@app.post("/api/campaign/generate-vision", tags=["Campaigns"])
@limiter.limit("5/minute")
async def api_campaign_generate_vision(
    request: Request,
    body: CampaignVisionGenerateRequest,
    auth: tuple = Depends(get_current_user_apikey),
    db: Session = Depends(get_db)
):
    from .database import Campaign
    from .campaigns import generate_omni_campaign_from_image
    import uuid
    import json
    import base64
    import binascii
    
    user, _ = auth
    
    allowed_image_types = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    mime_type = (body.mime_type or "image/jpeg").lower().strip()
    if mime_type not in allowed_image_types:
        raise HTTPException(status_code=400, detail="Unsupported image type.")

    raw_b64 = body.image_base64
    if "," in raw_b64:
        raw_b64 = raw_b64.split(",", 1)[1]
    try:
        img_bytes = base64.b64decode(raw_b64, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(status_code=400, detail="image_base64 must contain valid base64 data.") from None
    if not img_bytes:
        raise HTTPException(status_code=400, detail="Image data is empty.")
    if len(img_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image exceeds the 10 MB upload limit.")

    # Invariant: Atomic credit deduction before expensive Vision generation.
    monthly_used, purchased_used = reserve_user_generations(user.id, 1, db)

    try:
        data = _sanitize_campaign_assets(generate_omni_campaign_from_image(
            image_bytes=img_bytes,
            mime_type=mime_type,
            keyword=body.keyword or "",
            extra_context=body.extra_context or ""
        ))
        
        cid = str(uuid.uuid4())
        prod_title = data.get("detected_product_name", body.keyword or "Product")
        name = f"Vision Campaign: {prod_title}"
        
        db.add(Campaign(id=cid, user_id=user.id, name=name, assets=json.dumps(data)))
        db.commit()
        return {"id": cid, "name": name, "assets": data}
    except ValueError as e:
        refund_user_generations(user.id, monthly_used, purchased_used, db)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        refund_user_generations(user.id, monthly_used, purchased_used, db)
        raise HTTPException(status_code=500, detail="Vision generation failed due to an internal error. Your balance was refunded.")

@app.post("/api/campaign/push", tags=["Campaigns"])
@limiter.limit("5/minute")
async def api_campaign_push(request: Request, body: CampaignPushRequest, background_tasks: BackgroundTasks, auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .database import Campaign, UserIntegration, PushJob
    from .auth import decrypt_credentials
    from .integrations import background_push
    import json
    import uuid
    user, _ = auth
    camp = db.query(Campaign).filter(Campaign.id == body.campaign_id, Campaign.user_id == user.id).first()
    if not camp:
        raise HTTPException(status_code=404, detail="Campaign not found")
    assets = json.loads(camp.assets)
    jobs = []
    for asset_type, dest in body.destinations.items():
        if not isinstance(dest, dict):
            continue
        platform = dest.get("platform")
        meta = dest.get("metadata", {})
        integration = db.query(UserIntegration).filter(UserIntegration.user_id == user.id, UserIntegration.platform == platform).first() if platform else None
        if not integration:
            continue
        try:
            creds = json.loads(decrypt_credentials(integration.credentials))
        except Exception:
            continue
        if asset_type == "blog" and "blog_post" in assets:
            title = assets["blog_post"]["title"]
            content = assets["blog_post"]["content"]
        elif asset_type == "email" and assets.get("email_drip"):
            title = assets["email_drip"][0]["subject"]
            content = assets["email_drip"][0]["body"]
        else:
            continue
        if not content:
            continue
        content = sanitize_html(content)
        if not content.strip():
            continue
        title = _clean_text(title, 255) or "Generated via KopyKat"
        jid = str(uuid.uuid4())
        db.add(PushJob(id=jid, user_id=user.id, platform=platform, status="pending"))
        jobs.append(jid)
        background_tasks.add_task(background_push, platform, creds, title, content, meta, integration.id, jid)
    db.commit()
    return JSONResponse(status_code=202, content={"message": "Omni-Push accepted", "job_ids": jobs})

@app.get("/api/connector", tags=["Connectors"])
async def api_connector_list(auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .database import CustomConnector
    user, _ = auth
    connectors = db.query(CustomConnector).filter(CustomConnector.user_id == user.id).order_by(CustomConnector.created_at.desc()).all()
    return [{
        "id": c.id,
        "platform_name": c.platform_name,
        "source_url": c.source_url,
        "base_url": c.base_url,
        "operation_count": c.operation_count,
        "authentication_modes": c.authentication_modes.split(",") if c.authentication_modes else [],
        "status": c.status,
        "created_at": c.created_at
    } for c in connectors]

@app.get("/api/connector/{connector_id}", tags=["Connectors"])
async def api_connector_get(connector_id: str, auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .database import CustomConnector
    user, _ = auth
    c = db.query(CustomConnector).filter(CustomConnector.id == connector_id, CustomConnector.user_id == user.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Connector not found.")
    import json
    return {
        "id": c.id,
        "platform_name": c.platform_name,
        "source_url": c.source_url,
        "base_url": c.base_url,
        "spec": json.loads(c.spec),
        "authentication_modes": c.authentication_modes.split(",") if c.authentication_modes else [],
        "status": c.status,
        "created_at": c.created_at
    }

@app.post("/api/connector/{connector_id}/credentials", tags=["Connectors"])
async def api_connector_save_credentials(connector_id: str, body: ConnectorCredentialsRequest, auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .database import CustomConnector, UserIntegration
    from .auth import encrypt_credentials
    import json
    import uuid
    user, _ = auth
    
    c = db.query(CustomConnector).filter(CustomConnector.id == connector_id, CustomConnector.user_id == user.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Connector not found.")
        
    enc_creds = encrypt_credentials(json.dumps(body.credentials))
    platform_key = f"custom_{c.id}"
    
    existing = db.query(UserIntegration).filter(UserIntegration.user_id == user.id, UserIntegration.platform == platform_key).first()
    if existing:
        existing.credentials = enc_creds
        existing.status = "connected"
    else:
        db.add(UserIntegration(
            id=str(uuid.uuid4()),
            user_id=user.id,
            platform=platform_key,
            credentials=enc_creds,
            status="connected"
        ))
    
    c.status = "validated"
    db.commit()
    return {"message": "Connector credentials securely encrypted and saved.", "status": "validated"}

@app.post("/api/connector/{connector_id}/test", tags=["Connectors"])
@limiter.limit("10/minute")
async def api_connector_test(request: Request, connector_id: str, body: ConnectorTestRequest, auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .database import CustomConnector, UserIntegration, ConnectorAuditLog
    from .connector_registry import execute_operation, ConnectorError
    from .auth import decrypt_credentials
    import json
    import uuid
    user, _ = auth
    
    c = db.query(CustomConnector).filter(CustomConnector.id == connector_id, CustomConnector.user_id == user.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Connector not found.")
        
    spec = json.loads(c.spec)
    
    # Retrieve credentials if stored
    auth_headers = {}
    platform_key = f"custom_{c.id}"
    integ = db.query(UserIntegration).filter(UserIntegration.user_id == user.id, UserIntegration.platform == platform_key).first()
    if integ:
        try:
            creds = json.loads(decrypt_credentials(integ.credentials))
            if "api_key" in creds:
                auth_headers["Authorization"] = f"Bearer {creds['api_key']}"
            elif "access_token" in creds:
                auth_headers["Authorization"] = f"Bearer {creds['access_token']}"
        except Exception:
            pass
            
    try:
        res = execute_operation(
            spec=spec,
            operation_name=body.operation_name,
            headers=body.headers,
            query=body.query,
            auth_headers=auth_headers
        )
        
        # Audit Log
        db.add(ConnectorAuditLog(
            id=str(uuid.uuid4()),
            connector_id=c.id,
            user_id=user.id,
            operation_name=body.operation_name,
            status="success" if res.get("status_code", 500) < 400 else "failed",
            status_code=res.get("status_code"),
            details=f"Test executed against {c.platform_name}"
        ))
        db.commit()
        return res
    except ConnectorError as e:
        db.add(ConnectorAuditLog(
            id=str(uuid.uuid4()),
            connector_id=c.id,
            user_id=user.id,
            operation_name=body.operation_name,
            status="blocked",
            status_code=400,
            details=str(e)[:1000]
        ))
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Connector test execution failed.")

@app.post("/api/connector/{connector_id}/toggle", tags=["Connectors"])
async def api_connector_toggle(connector_id: str, body: ConnectorToggleRequest, auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .database import CustomConnector, ConnectorAuditLog
    import uuid
    user, _ = auth
    
    c = db.query(CustomConnector).filter(CustomConnector.id == connector_id, CustomConnector.user_id == user.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Connector not found.")
        
    new_status = "active" if body.active else "disabled"
    c.status = new_status
    
    db.add(ConnectorAuditLog(
        id=str(uuid.uuid4()),
        connector_id=c.id,
        user_id=user.id,
        operation_name="toggle_status",
        status="success",
        status_code=200,
        details=f"Status set to {new_status}"
    ))
    db.commit()
    return {"id": c.id, "status": c.status}


# --- COMPETITOR REVIEW MINING ROUTE ---
@app.post("/api/competitor/mine-reviews", response_model=CompetitorMineResponse, tags=["Competitor Mining"])
@limiter.limit("10/minute")
async def api_mine_competitor_reviews(
    request: Request,
    body: CompetitorMineRequest,
    auth: tuple = Depends(get_current_user_apikey),
    db: Session = Depends(get_db)
):
    from .database import CompetitorAudit
    from .ai_engine import mine_competitor_reviews
    import uuid
    import json

    user, _ = auth

    # Centralized dual-bucket reservation (monthly before purchased)
    monthly_used, purchased_used = reserve_user_generations(user.id, 1, db)

    try:
        data = await mine_competitor_reviews(
            product_name=body.product_name,
            competitor_name=body.competitor_name or "Competitor",
            reviews_text=body.reviews_text
        )

        audit_id = str(uuid.uuid4())
        audit = CompetitorAudit(
            id=audit_id,
            user_id=user.id,
            product_name=body.product_name,
            competitor_name=body.competitor_name or "Competitor",
            extracted_flaws=json.dumps(data.get("extracted_flaws", [])),
            counter_copy=json.dumps(data)
        )
        db.add(audit)
        db.commit()

        return CompetitorMineResponse(
            id=audit_id,
            product_name=body.product_name,
            competitor_name=body.competitor_name or "Competitor",
            extracted_flaws=data.get("extracted_flaws", []),
            counter_description=data.get("counter_description", ""),
            comparison_points=data.get("comparison_points", []),
            ad_hooks=data.get("ad_hooks", [])
        )
    except Exception as e:
        db.rollback()
        # Atomic dual-bucket refund on failure
        refund_user_generations(user.id, monthly_used, purchased_used, db)
        logger.error("Competitor review mining failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Review mining analysis failed. Your balance was refunded."
        )


# --- BYOK CUSTOM AI KEY ROUTES ---
@app.get("/api/user/custom-ai-key", response_model=CustomAIKeyResponse, tags=["BYOK"])
async def get_custom_ai_key_status(auth: tuple = Depends(get_current_user_apikey)):
    user, _ = auth
    has_key = bool(user.custom_ai_key_encrypted)
    is_unlimited = (user.plan == "megastore" and has_key)
    return CustomAIKeyResponse(
        has_custom_key=has_key,
        provider=user.custom_ai_provider,
        unlimited_active=is_unlimited
    )

@app.post("/api/user/custom-ai-key", tags=["BYOK"])
@limiter.limit("10/minute")
async def set_custom_ai_key(request: Request, body: CustomAIKeyRequest, auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .auth import encrypt_credentials
    user, _ = auth
    if user.plan != "megastore":
        raise HTTPException(status_code=403, detail="Custom AI API Key (BYOK) is exclusively available on the Megastore Infrastructure tier.")

    encrypted_key = encrypt_credentials(body.api_key.strip())
    user.custom_ai_key_encrypted = encrypted_key
    user.custom_ai_provider = body.provider
    db.commit()
    return {
        "success": True,
        "has_custom_key": True,
        "provider": user.custom_ai_provider,
        "unlimited_active": True,
        "message": "Custom AI provider key securely saved. Future generations can use the configured provider."
    }

@app.delete("/api/user/custom-ai-key", tags=["BYOK"])
async def delete_custom_ai_key(auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    user, _ = auth
    user.custom_ai_key_encrypted = None
    user.custom_ai_provider = None
    db.commit()
    return {"success": True, "message": "Custom AI Key removed. Reverted to standard plan quota."}


# --- INVENTORY BALANCER ROUTES ---
@app.get("/api/inventory", response_model=list[InventoryItemResponse], tags=["Inventory Balancer"])
async def list_inventory_items(auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .database import InventoryItem
    import json
    user, _ = auth
    items = db.query(InventoryItem).filter(InventoryItem.user_id == user.id).order_by(InventoryItem.updated_at.desc()).all()
    results = []
    for it in items:
        try:
            p_stock = json.loads(it.platform_stock or "{}")
        except Exception:
            p_stock = {}
        results.append(InventoryItemResponse(
            id=it.id,
            sku=it.sku,
            title=it.title,
            total_stock=it.total_stock,
            platform_stock=p_stock,
            updated_at=it.updated_at
        ))
    return results

@app.post("/api/inventory/item", response_model=InventoryItemResponse, tags=["Inventory Balancer"])
async def create_or_update_inventory_item(body: InventoryItemCreate, auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .database import InventoryItem
    import uuid
    import json
    user, _ = auth
    clean_sku = body.sku.strip().upper()
    item = db.query(InventoryItem).filter(InventoryItem.user_id == user.id, InventoryItem.sku == clean_sku).first()
    if item:
        item.title = body.title.strip()
        item.total_stock = body.total_stock
        item.updated_at = datetime.utcnow()
    else:
        item = InventoryItem(
            id=str(uuid.uuid4()),
            user_id=user.id,
            sku=clean_sku,
            title=body.title.strip(),
            total_stock=body.total_stock,
            platform_stock="{}",
            updated_at=datetime.utcnow()
        )
        db.add(item)
    db.commit()
    db.refresh(item)
    try:
        p_stock = json.loads(item.platform_stock or "{}")
    except Exception:
        p_stock = {}
    return InventoryItemResponse(
        id=item.id,
        sku=item.sku,
        title=item.title,
        total_stock=item.total_stock,
        platform_stock=p_stock,
        updated_at=item.updated_at
    )

@app.post("/api/inventory/webhook/{platform}", tags=["Inventory Balancer"])
@limiter.limit("60/minute")
async def inventory_webhook(
    request: Request,
    platform: str,
    body: InventoryWebhookPayload,
    auth: tuple = Depends(get_current_user_apikey),
    db: Session = Depends(get_db)
):
    from .inventory import SUPPORTED_INVENTORY_PLATFORMS, normalize_platform_name, sync_inventory_across_platforms
    user, _ = auth
    normalized_platform = normalize_platform_name(platform)
    if normalized_platform not in SUPPORTED_INVENTORY_PLATFORMS:
        raise HTTPException(status_code=400, detail="Unsupported inventory platform")
    event_id = body.order_id or request.headers.get("X-Event-ID", "")
    res = sync_inventory_across_platforms(
        user_id=user.id,
        sku=body.sku,
        delta=body.quantity_delta,
        trigger_platform=normalized_platform,
        db=db,
        event_id=event_id
    )
    return res

@app.post("/api/inventory/reconcile", tags=["Inventory Balancer"])
async def reconcile_inventory(
    sku: str = Query(..., min_length=1, max_length=100),
    canonical_stock: int = Query(..., ge=0, le=2_000_000),
    auth: tuple = Depends(get_current_user_apikey),
    db: Session = Depends(get_db)
):
    from .inventory import reconcile_inventory_sku
    user, _ = auth
    res = reconcile_inventory_sku(
        user_id=user.id,
        sku=sku,
        canonical_stock=canonical_stock,
        db=db
    )
    return res

@app.get("/api/inventory/logs", response_model=list[InventorySyncLogResponse], tags=["Inventory Balancer"])
async def list_inventory_sync_logs(auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .database import InventorySyncLog
    import json
    user, _ = auth
    logs = db.query(InventorySyncLog).filter(InventorySyncLog.user_id == user.id).order_by(InventorySyncLog.created_at.desc()).limit(50).all()
    results = []
    for l in logs:
        try:
            fanout = json.loads(l.fanout_results or "{}")
        except Exception:
            fanout = {}
        results.append(InventorySyncLogResponse(
            id=l.id,
            sku=l.sku,
            trigger_platform=l.trigger_platform,
            quantity_change=l.quantity_change,
            new_quantity=l.new_quantity,
            fanout_results=fanout,
            created_at=l.created_at
        ))
    return results


# --- POST-PURCHASE REVIEW & UGC ROUTES ---
@app.post("/api/reviews/drip-templates", response_model=PostPurchaseDripResponse, tags=["Reviews & UGC"])
async def generate_drip_sequence(body: PostPurchaseDripRequest, auth: tuple = Depends(get_current_user_apikey)):
    from .reviews_ugc import generate_post_purchase_drip
    import uuid
    emails = generate_post_purchase_drip(
        product_name=body.product_name,
        brand_tone=body.brand_tone or "Warm and helpful",
        incentive=body.incentive_offer or "15% off your next order"
    )
    return PostPurchaseDripResponse(
        id=str(uuid.uuid4()),
        product_name=body.product_name,
        drip_emails=emails
    )

@app.post("/api/reviews/submit", response_model=CustomerReviewResponse, tags=["Reviews & UGC"])
@limiter.limit("30/minute")
async def submit_customer_review(
    request: Request,
    body: CustomerReviewSubmitRequest,
    auth: tuple = Depends(get_current_user_apikey),
    db: Session = Depends(get_db)
):
    from .reviews_ugc import classify_review_sentiment_and_reply
    from .database import CustomerReview
    import uuid
    user, _ = auth
    analysis = classify_review_sentiment_and_reply(
        customer_name=body.customer_name,
        product_name=body.product_name,
        rating=body.rating,
        review_text=body.review_text
    )

    review_obj = CustomerReview(
        id=str(uuid.uuid4()),
        user_id=user.id,
        customer_name=body.customer_name.strip(),
        customer_email=body.customer_email.strip() if body.customer_email else None,
        product_name=body.product_name.strip(),
        rating=body.rating,
        review_text=body.review_text.strip(),
        sentiment=analysis["sentiment"],
        status=analysis["status"],
        draft_reply=analysis["draft_reply"],
        created_at=datetime.utcnow()
    )
    db.add(review_obj)
    db.commit()
    db.refresh(review_obj)

    return CustomerReviewResponse(
        id=review_obj.id,
        customer_name=review_obj.customer_name,
        customer_email=review_obj.customer_email,
        product_name=review_obj.product_name,
        rating=review_obj.rating,
        review_text=review_obj.review_text,
        sentiment=review_obj.sentiment,
        status=review_obj.status,
        draft_reply=review_obj.draft_reply,
        created_at=review_obj.created_at
    )

@app.get("/api/reviews", response_model=list[CustomerReviewResponse], tags=["Reviews & UGC"])
async def list_customer_reviews(auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .database import CustomerReview
    user, _ = auth
    reviews = db.query(CustomerReview).filter(CustomerReview.user_id == user.id).order_by(CustomerReview.created_at.desc()).limit(100).all()
    return [
        CustomerReviewResponse(
            id=r.id,
            customer_name=r.customer_name,
            customer_email=r.customer_email,
            product_name=r.product_name,
            rating=r.rating,
            review_text=r.review_text,
            sentiment=r.sentiment,
            status=r.status,
            draft_reply=r.draft_reply,
            created_at=r.created_at
        ) for r in reviews
    ]


# --- PRICE & MARGIN MONITOR ROUTES ---
@app.get("/api/pricing/items", response_model=list[PriceMarginItemResponse], tags=["Price & Margin Monitor"])
async def list_price_margin_items(auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .database import PriceMarginItem
    user, _ = auth
    items = db.query(PriceMarginItem).filter(PriceMarginItem.user_id == user.id).order_by(PriceMarginItem.updated_at.desc()).all()
    return items

@app.post("/api/pricing/item", response_model=PriceMarginItemResponse, tags=["Price & Margin Monitor"])
async def create_or_update_price_item(
    body: PriceMarginItemCreate,
    auth: tuple = Depends(get_current_user_apikey),
    db: Session = Depends(get_db)
):
    from .database import PriceMarginItem
    from .pricing_monitor import compute_pricing_analysis
    import uuid

    user, _ = auth
    clean_sku = body.sku.strip().upper()
    analysis = compute_pricing_analysis(
        cogs=body.cogs_usd,
        selling_price=body.selling_price_usd,
        competitor_price=body.competitor_price_usd,
        target_margin=body.target_margin_pct if body.target_margin_pct is not None else 40.0
    )

    item = db.query(PriceMarginItem).filter(PriceMarginItem.user_id == user.id, PriceMarginItem.sku == clean_sku).first()
    if item:
        item.product_name = body.product_name.strip()
        item.cogs_usd = body.cogs_usd
        item.selling_price_usd = body.selling_price_usd
        item.competitor_price_usd = body.competitor_price_usd
        item.target_margin_pct = body.target_margin_pct if body.target_margin_pct is not None else 40.0
        item.current_margin_pct = analysis["current_margin_pct"]
        item.profit_per_unit_usd = analysis["profit_per_unit_usd"]
        item.status = analysis["status"]
        item.recommendation = analysis["recommendation"]
        item.updated_at = datetime.utcnow()
    else:
        item = PriceMarginItem(
            id=str(uuid.uuid4()),
            user_id=user.id,
            sku=clean_sku,
            product_name=body.product_name.strip(),
            cogs_usd=body.cogs_usd,
            selling_price_usd=body.selling_price_usd,
            competitor_price_usd=body.competitor_price_usd,
            target_margin_pct=body.target_margin_pct if body.target_margin_pct is not None else 40.0,
            current_margin_pct=analysis["current_margin_pct"],
            profit_per_unit_usd=analysis["profit_per_unit_usd"],
            status=analysis["status"],
            recommendation=analysis["recommendation"],
            updated_at=datetime.utcnow()
        )
        db.add(item)

    db.commit()
    db.refresh(item)
    return item

@app.delete("/api/pricing/item/{item_id}", tags=["Price & Margin Monitor"])
async def delete_price_item(item_id: str, auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .database import PriceMarginItem
    user, _ = auth
    item = db.query(PriceMarginItem).filter(PriceMarginItem.id == item_id, PriceMarginItem.user_id == user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
    return {"success": True, "message": "Item deleted"}


# --- SHOPIFY DIRECT IMPORT ROUTES ---
@app.post("/api/catalog/import-shopify", response_model=ShopifyImportResponse, tags=["Catalog Automation"])
@limiter.limit("15/minute")
async def api_import_shopify_catalog(
    request: Request,
    body: ShopifyImportRequest,
    auth: tuple = Depends(get_current_user_apikey),
    db: Session = Depends(get_db)
):
    from .shopify_import import import_shopify_catalog_direct
    from .database import UserIntegration
    from .auth import decrypt_credentials
    import json

    user, _ = auth
    shop_url = body.shop_url
    token = body.access_token

    # If credentials not provided in payload, look up connected Shopify integration
    if not shop_url or not token:
        integ = db.query(UserIntegration).filter(
            UserIntegration.user_id == user.id,
            UserIntegration.platform == "shopify",
            UserIntegration.status == "connected"
        ).first()

        if integ and integ.credentials:
            try:
                decrypted = decrypt_credentials(integ.credentials)
                creds = json.loads(decrypted) if decrypted.startswith("{") else {"token": decrypted}
                token = creds.get("token") or creds.get("access_token")
                shop_url = creds.get("shop_url") or creds.get("shop")
            except Exception:
                pass

    if not shop_url or not token:
        return ShopifyImportResponse(
            success=False,
            total_imported=0,
            items=[],
            error="Please provide your Shopify store URL and Admin API Access Token, or connect Shopify in Integrations."
        )

    res = await import_shopify_catalog_direct(
        shop_url=shop_url,
        access_token=token,
        limit=body.limit or 50
    )

    return ShopifyImportResponse(
        success=res.get("success", False),
        total_imported=res.get("total_imported", 0),
        items=res.get("items", []),
        error=res.get("error")
    )


# --- OPPORTUNITY LEADS ROUTE ---
@app.get("/api/leads", tags=["Opportunity Scout"])
async def list_opportunity_leads(auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .database import OpportunityLog
    leads = db.query(OpportunityLog).order_by(OpportunityLog.created_at.desc()).limit(50).all()
    return [
        {
            "id": l.id,
            "platform": l.platform,
            "post_title": l.post_title,
            "post_url": l.post_url,
            "draft_reply": l.draft_reply,
            "score": l.score,
            "created_at": l.created_at
        } for l in leads
    ]


# --- GROWTH ENGINES: SEO & DRIP ANALYTICS ---
@app.get("/api/seo/analytics", tags=["Growth Engines"])
async def get_seo_analytics(auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .database import BlogPost
    posts = db.query(BlogPost).filter(BlogPost.published == True).all()
    total_words = sum(p.word_count for p in posts)
    base_url = PUBLIC_BASE_URL
    return {
        "total_posts": len(posts),
        "total_words_generated": total_words,
        "sitemap_url": f"{base_url}/sitemap.xml",
        "robots_url": f"{base_url}/robots.txt",
        "indexing_status": "active",
        "recent_articles": [
            {
                "id": p.id,
                "title": p.title,
                "slug": p.slug,
                "url": f"{base_url}/blog/{p.slug}",
                "word_count": p.word_count,
                "created_at": p.created_at
            } for p in sorted(posts, key=lambda x: x.created_at, reverse=True)[:10]
        ]
    }

@app.post("/api/seo/ping-index", tags=["Growth Engines"])
async def ping_search_engines(auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    import httpx
    base_url = PUBLIC_BASE_URL
    sitemap_url = f"{base_url}/sitemap.xml"
    
    ping_targets = [
        f"https://www.google.com/ping?sitemap={sitemap_url}",
        f"https://www.bing.com/ping?sitemap={sitemap_url}"
    ]
    
    results = []
    async with httpx.AsyncClient(timeout=5.0, follow_redirects=False, trust_env=False) as client:
        for target in ping_targets:
            try:
                resp = await client.get(target)
                results.append({"engine": "google" if "google" in target else "bing", "status": resp.status_code})
            except Exception:
                logger.warning("Search engine ping failed", extra={"target": target}, exc_info=True)
                results.append({"engine": "google" if "google" in target else "bing", "status": "error"})
                
    return {
        "success": True,
        "sitemap_url": sitemap_url,
        "pings": results,
        "message": "Search engine crawlers successfully notified of dynamic sitemap updates."
    }

@app.get("/api/drip/analytics", tags=["Growth Engines"])
async def get_drip_analytics(auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    from .database import User, DripLog
    total_free_users = db.query(User).filter(User.plan == "free").count()
    total_paid_users = db.query(User).filter(User.plan != "free").count()
    
    day2_sent = db.query(DripLog).filter(DripLog.step == 2).count()
    day4_sent = db.query(DripLog).filter(DripLog.step == 4).count()
    day7_sent = db.query(DripLog).filter(DripLog.step == 7).count()
    
    return {
        "funnel": {
            "total_free_users": total_free_users,
            "day2_value_drips_sent": day2_sent,
            "day4_case_study_drips_sent": day4_sent,
            "day7_upgrade_drips_sent": day7_sent,
            "active_paying_subscribers": total_paid_users
        },
        "conversion_rate_pct": round((total_paid_users / (total_free_users + total_paid_users) * 100), 1) if (total_free_users + total_paid_users) > 0 else 0.0,
        "status": "autonomous_active"
    }

# --- BRAND VOICE PERSONA ENGINE ---
@app.get("/api/brand-persona", response_model=Optional[BrandPersonaResponse], tags=["Brand Persona"])
async def get_brand_persona(auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    user = auth[0]
    from .database import BrandPersona
    persona = db.query(BrandPersona).filter(BrandPersona.user_id == user.id).first()
    if not persona:
        return None
    return BrandPersonaResponse(
        id=persona.id,
        brand_name=persona.brand_name,
        brand_voice_tone=persona.brand_voice_tone,
        target_audience=persona.target_audience,
        rules_and_guidelines=persona.rules_and_guidelines,
        sample_copy=persona.sample_copy,
        updated_at=persona.updated_at
    )

@app.post("/api/brand-persona", response_model=BrandPersonaResponse, tags=["Brand Persona"])
async def save_brand_persona(body: BrandPersonaRequest, auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    user = auth[0]
    from .billing import user_has_entitlement
    if not user_has_entitlement(user, "brand_voice_training", db):
        raise HTTPException(status_code=403, detail="Brand Voice Training add-on or Megastore plan required")
    from .database import BrandPersona
    persona = db.query(BrandPersona).filter(BrandPersona.user_id == user.id).first()
    if persona:
        persona.brand_name = body.brand_name
        persona.brand_voice_tone = body.brand_voice_tone
        persona.target_audience = body.target_audience
        persona.rules_and_guidelines = body.rules_and_guidelines
        persona.sample_copy = body.sample_copy
        persona.updated_at = datetime.utcnow()
    else:
        persona = BrandPersona(
            id=str(uuid.uuid4()),
            user_id=user.id,
            brand_name=body.brand_name,
            brand_voice_tone=body.brand_voice_tone,
            target_audience=body.target_audience,
            rules_and_guidelines=body.rules_and_guidelines,
            sample_copy=body.sample_copy,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(persona)
    db.commit()
    db.refresh(persona)
    return BrandPersonaResponse(
        id=persona.id,
        brand_name=persona.brand_name,
        brand_voice_tone=persona.brand_voice_tone,
        target_audience=persona.target_audience,
        rules_and_guidelines=persona.rules_and_guidelines,
        sample_copy=persona.sample_copy,
        updated_at=persona.updated_at
    )


# --- MARKETPLACE LISTING OPTIMIZER ---
@app.post("/api/optimizer/marketplace-listing", response_model=MarketplaceOptimizeResponse, tags=["Listing Optimizer"])
async def optimize_listing_endpoint(body: MarketplaceOptimizeRequest, auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    user = auth[0]
    from .billing import user_has_entitlement
    if not user_has_entitlement(user, "marketplace_optimizer_pack", db):
        raise HTTPException(status_code=403, detail="Marketplace Listing Optimizer Pack add-on or Megastore plan required")
    from .database import BrandPersona
    persona_row = db.query(BrandPersona).filter(BrandPersona.user_id == user.id).first()
    persona_dict = None
    if persona_row:
        persona_dict = {
            "brand_name": persona_row.brand_name,
            "brand_voice_tone": persona_row.brand_voice_tone,
            "rules_and_guidelines": persona_row.rules_and_guidelines
        }

    from .ai_engine import optimize_marketplace_listing
    res = await optimize_marketplace_listing(
        product_name=body.product_name,
        platform=body.platform,
        raw_details=body.raw_details,
        keywords=body.keywords,
        target_audience=body.target_audience,
        brand_persona=persona_dict
    )

    return MarketplaceOptimizeResponse(
        platform=res.get("platform", body.platform),
        product_name=res.get("product_name", body.product_name),
        optimized_title=res.get("optimized_title", body.product_name),
        bullet_points=res.get("bullet_points", []),
        meta_description=res.get("meta_description"),
        backend_search_terms=res.get("backend_search_terms"),
        tags=res.get("tags", []),
        short_hooks=res.get("short_hooks", []),
        hashtags=res.get("hashtags", []),
        sub_title=res.get("sub_title") or res.get("subtitle"),
        item_specifics=res.get("item_specifics"),
        structured_description=res.get("structured_description", body.raw_details),
        compliance_score=res.get("compliance_score", 95)
    )


# --- À-LA-CARTE ADD-ONS CATALOG & CHECKOUT ---
@app.get("/api/billing/addons", tags=["Billing Add-ons"])
async def list_addons():
    from .billing import ADD_ONS
    return [
        {
            "key": k,
            "name": v["name"],
            "price_usd": v["price_usd"],
            "billing_type": v["billing_type"],
            "description": v["description"],
            "features": v["features"]
        } for k, v in ADD_ONS.items()
    ]

@app.post("/billing/addon/checkout", tags=["Billing Add-ons"])
async def create_addon_checkout(body: AddOnCheckoutRequest, auth: tuple = Depends(get_current_user_apikey), db: Session = Depends(get_db)):
    user = auth[0]
    from .billing import ADD_ONS, get_or_create_stripe_customer
    if body.addon_key not in ADD_ONS:
        raise HTTPException(status_code=400, detail="Invalid add-on product key.")

    addon = ADD_ONS[body.addon_key]
    base_url = PUBLIC_BASE_URL
    
    import stripe
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Stripe is not configured. Payment gateway unavailable.")

    try:
        customer_id = get_or_create_stripe_customer(user, db)
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": addon["name"],
                        "description": addon["description"],
                    },
                    "unit_amount": int(addon["price_usd"] * 100),
                    **({"recurring": {"interval": "month"}} if addon["billing_type"] == "monthly" else {})
                },
                "quantity": 1,
            }],
            mode="subscription" if addon["billing_type"] == "monthly" else "payment",
            metadata={"user_id": user.id, "addon_key": body.addon_key, "type": "addon"},
            client_reference_id=user.id,
            success_url=f"{base_url}/dashboard?addon_success={body.addon_key}",
            cancel_url=f"{base_url}/dashboard?addon_cancel=1",
        )
        return {"checkout_url": session.url, "session_id": session.id, "addon": addon["name"]}
    except Exception as e:
        logger.error("Stripe add-on session creation error: %s", e)
        raise HTTPException(status_code=503, detail="Payment gateway error. Please try again later.")
