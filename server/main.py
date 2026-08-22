"""
main.py — FastAPI application entry point.
All routes, startup/shutdown lifecycle, and static file serving.
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import bleach
from fastapi import (
    FastAPI, Depends, HTTPException, Request, Header,
    BackgroundTasks, status
)
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
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
    RequestPasswordReset, ResetPasswordSubmit,
    IntegrationSaveRequest, PushRequest,
    CampaignGenerateRequest, CampaignPushRequest,
    UserRegister, UserLogin, TokenResponse, UserProfile,
    APIKeyCreate, APIKeyResponse, APIKeyCreated,
    GenerateRequest, GenerateResponse,
    CheckoutRequest, OneTimeGenerationsRequest, CheckoutResponse,
    SubscriptionStatus, UsageSummary, HealthResponse,
)
from .auth import (
    register_user, authenticate_user, create_access_token,
    create_user_api_key, revoke_api_key,
    get_current_user_jwt, get_current_user_apikey,
)
from .ai_engine import generate_copy
from .billing import (
    create_subscription_checkout, create_one_time_checkout,
    handle_stripe_webhook, get_total_revenue, PLANS, ONE_TIME_GENERATIONS,
)
from .marketing import generate_seo_post
from .scheduler import create_scheduler

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── App setup ──────────────────────────────────────────────────────────────────

APP_VERSION  = "1.0.0"
BASE_DIR     = Path(__file__).parent.parent
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")

# ── Rate limiter ───────────────────────────────────────────────────────────────
# Uses client IP for unauthenticated routes; stricter limits on auth/generate.

limiter = Limiter(key_func=get_remote_address)


import sentry_sdk

SENTRY_DSN = os.environ.get("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )

app = FastAPI(
    title="KopyKat",
    description="Instant AI-powered marketing copy. Automated. Always on.",
    version=APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS — restrict to explicit allow-list ─────────────────────────────────────
# Set ALLOWED_ORIGINS in your .env as a comma-separated list of allowed origins.
# Example: ALLOWED_ORIGINS=https://kopykat-ai.onrender.com,https://www.kopykat.ai
_raw_origins = os.getenv("ALLOWED_ORIGINS", "https://kopykat-ai.onrender.com")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,      # explicit list — never "*"
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Admin-Secret"],
)

from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])
)

# ── HTML sanitization allow-list ───────────────────────────────────────────────
# Used for AI-generated blog post content before it is inserted into the page.

_ALLOWED_TAGS = [
    "p", "h2", "h3", "h4", "ul", "ol", "li",
    "strong", "em", "b", "i", "a", "br", "blockquote",
]
_ALLOWED_ATTRS = {"a": ["href", "title", "rel"]}


def sanitize_html(raw: str) -> str:
    """Strip dangerous tags/attributes from AI-generated HTML before rendering."""
    return bleach.clean(
        raw,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        strip=True,       # remove disallowed tags entirely (not just escape)
        strip_comments=True,
    )


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    logger.info("🚀 KopyKat starting up...")
    init_db()
    logger.info("✅ Database initialized")
    logger.info(f"🟢 KopyKat v{APP_VERSION} is live and running")
    # Note: Background tasks (APScheduler) are now run separately via worker.py
    # to prevent duplicate jobs when scaling horizontally.


@app.on_event("shutdown")
async def shutdown():
    logger.info("KopyKat shut down gracefully")


# ── Static files ───────────────────────────────────────────────────────────────

frontend_dir = BASE_DIR / "frontend"
if (frontend_dir / "static").exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir / "static")), name="static")


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def landing_page():
    """Serve the marketing landing page."""
    index = frontend_dir / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>KopyKat — Loading...</h1>")



@app.get("/manifest.json", include_in_schema=False)
async def get_manifest():
    return FileResponse(frontend_dir / "manifest.json")

@app.get("/sw.js", include_in_schema=False)
async def get_sw():
    return FileResponse(frontend_dir / "sw.js")

@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_page():
    """Serve the customer dashboard."""
    dash = frontend_dir / "dashboard.html"
    if dash.exists():
        return HTMLResponse(dash.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Dashboard — Loading...</h1>")


@app.get("/admin/trigger-seo", include_in_schema=False)
async def trigger_seo(
    background_tasks: BackgroundTasks,
    x_admin_secret: Optional[str] = Header(None, alias="x-admin-secret"),
):
    """
    Manually kickstart the SEO engine.
    Pass your ADMIN_SECRET in the X-Admin-Secret request header (not query param).
    The query-param pattern was removed because it leaks the secret into logs/history.
    """
    if not ADMIN_SECRET or x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    background_tasks.add_task(generate_seo_post)
    return {"status": "ok", "message": "SEO blog generation started in background. Check /blog in 30 seconds."}


@app.get("/blog", response_class=HTMLResponse, include_in_schema=False)
async def blog_index(db: Session = Depends(get_db)):
    """Serve the SEO blog index."""
    posts = db.query(BlogPost).filter(BlogPost.published == True).order_by(BlogPost.created_at.desc()).all()
    template_path = frontend_dir / "blog.html"
    if not template_path.exists():
        return HTMLResponse("<h1>Blog setup pending...</h1>")

    template = template_path.read_text(encoding="utf-8")

    items_html = ""
    for p in posts:
        date_str = p.created_at.strftime("%B %d, %Y")
        items_html += f'''
        <div class="card" style="margin-bottom: 24px;">
            <div style="font-size:12px; color:var(--muted); margin-bottom:8px;">{date_str}</div>
            <h2 style="margin-bottom:12px; font-size: 22px;"><a href="/blog/{p.slug}">{p.title}</a></h2>
            <p style="color:var(--muted); font-size:15px;">{p.meta_desc}</p>
        </div>
        '''
    if not items_html:
        items_html = "<p style='color:var(--muted);'>No posts yet. The AI is writing the first one!</p>"

    return HTMLResponse(template.replace("<!-- POSTS -->", items_html))


@app.get("/blog/{slug}", response_class=HTMLResponse, include_in_schema=False)
async def blog_post(slug: str, db: Session = Depends(get_db)):
    """Serve an individual SEO blog post."""
    post = db.query(BlogPost).filter(BlogPost.slug == slug, BlogPost.published == True).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    template_path = frontend_dir / "post.html"
    if not template_path.exists():
        return HTMLResponse("<h1>Post layout pending...</h1>")

    template = template_path.read_text(encoding="utf-8")
    date_str = post.created_at.strftime("%B %d, %Y")

    # Sanitize AI-generated HTML before inserting into the page
    safe_content = sanitize_html(post.content)

    html = template.replace("{{title}}", post.title)\
                   .replace("{{content}}", safe_content)\
                   .replace("{{meta_desc}}", post.meta_desc or "")\
                   .replace("{{date}}", date_str)

    return HTMLResponse(html)


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    return HealthResponse(status="ok", version=APP_VERSION, timestamp=datetime.utcnow())


@app.get("/api/plans", tags=["Billing"])
async def list_plans():
    """Returns all subscription plans and generation packs — no auth needed."""
    return {
        "subscriptions": {
            k: {
                "name":                 v["name"],
                "price_usd":            v["price_usd"],
                "monthly_generations":  v["monthly_generations"],
                "features":             v["features"],
            }
            for k, v in PLANS.items()
        },
        "one_time_generations": {
            k: {
                "name":        v["name"],
                "price_usd":   v["price_usd"],
                "generations": v["generations"],
            }
            for k, v in ONE_TIME_GENERATIONS.items()
        }
    }


# ══════════════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/auth/register", response_model=TokenResponse, tags=["Auth"])
@limiter.limit("5/minute")
async def register(request: Request, body: UserRegister, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Create a new account and return a JWT token."""
    user  = register_user(body.email, body.password, body.full_name, db)
    
    from .scheduler import _send_email
    subject = "Welcome to KopyKat 🚀"
    email_body = f"Hi {body.full_name or 'there'},<br><br>Welcome to KopyKat! Your account is loaded with 50 free generations.<br><br>Log in to generate your first high-converting copy: <a href='https://kopykat-ai.onrender.com/dashboard'>KopyKat Dashboard</a>"
    background_tasks.add_task(_send_email, subject, email_body, user.email)
    token = create_access_token(user.id, user.email)
    return TokenResponse(
        access_token=token,
        plan=user.plan,
        generations=user.generations,
    )


@app.post("/auth/login", response_model=TokenResponse, tags=["Auth"])
@limiter.limit("10/minute")
async def login(request: Request, body: UserLogin, db: Session = Depends(get_db)):
    """Log in with email + password, returns a JWT token."""
    user = authenticate_user(body.email, body.password, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user.id, user.email)
    return TokenResponse(
        access_token=token,
        plan=user.plan,
        generations=user.generations,
    )


@app.get("/auth/me", response_model=UserProfile, tags=["Auth"])
async def get_profile(current_user: User = Depends(get_current_user_jwt)):
    return current_user


# ══════════════════════════════════════════════════════════════════════════════
# API KEY ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/keys", response_model=APIKeyCreated, tags=["API Keys"])
async def create_api_key(
    body: APIKeyCreate,
    current_user: User = Depends(get_current_user_jwt),
    db: Session = Depends(get_db),
):
    """Create a new API key. The full key is shown ONCE — save it immediately."""
    raw_key, api_key = create_user_api_key(current_user, body.name, db)
    return APIKeyCreated(
        id=api_key.id,
        key_prefix=api_key.key_prefix,
        name=api_key.name,
        is_active=api_key.is_active,
        last_used=api_key.last_used,
        requests_today=api_key.requests_today,
        created_at=api_key.created_at,
        raw_key=raw_key,
    )


@app.get("/api/keys", response_model=list[APIKeyResponse], tags=["API Keys"])
async def list_api_keys(
    current_user: User = Depends(get_current_user_jwt),
    db: Session = Depends(get_db),
):
    """List all API keys for the current user (prefix only — no raw keys)."""
    keys = db.query(APIKey).filter(
        APIKey.user_id == current_user.id,
        APIKey.is_active == True,
    ).all()
    return keys


@app.delete("/api/keys/{key_id}", tags=["API Keys"])
async def delete_api_key(
    key_id: str,
    current_user: User = Depends(get_current_user_jwt),
    db: Session = Depends(get_db),
):
    """Revoke an API key."""
    if not revoke_api_key(key_id, current_user, db):
        raise HTTPException(status_code=404, detail="Key not found")
    return {"status": "revoked"}


# ══════════════════════════════════════════════════════════════════════════════
# AI GENERATION ROUTE  ← The core product
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/generate", response_model=GenerateResponse, tags=["Generate"])
@limiter.limit("60/minute")
async def generate(
    request: Request,
    body: GenerateRequest,
    auth: tuple = Depends(get_current_user_apikey),
    db: Session = Depends(get_db),
):
    """
    Generate marketing copy. Requires a valid API key in the Authorization header.

    Example:
        curl -X POST https://your-app.onrender.com/api/generate \\
          -H "Authorization: Bearer sc_your_api_key_here" \\
          -H "Content-Type: application/json" \\
          -d '{"type": "product_description", "context": "Wireless earbuds with 40h battery", "tone": "bold", "variations": 2}'
    """
    user, api_key = auth

    # ── Atomic generation deduction ──────────────────────────────────────────
    # 1 requested variation = 1 generation. Fair, predictable, transparent.
    generations_cost = body.variations

    rows_updated = db.execute(
        text(
            "UPDATE users SET generations = generations - :cost "
            "WHERE id = :uid AND generations >= :cost"
        ),
        {"cost": generations_cost, "uid": user.id},
    ).rowcount
    db.commit()

    if rows_updated == 0:
        raise HTTPException(
            status_code=402,
            detail="No generations remaining. Upgrade your plan or buy a generation pack at /dashboard",
        )

    # Run generation
    try:
        result = await generate_copy(
            copy_type=body.type,
            context=body.context,
            tone=body.tone or "professional",
            variations=body.variations,
            max_tokens=body.max_words,
            user_id=user.id,
            db=db,
        )
    except Exception:
        # Refund generations if AI call fails entirely
        db.execute(
            text("UPDATE users SET generations = generations + :cost WHERE id = :uid"),
            {"cost": generations_cost, "uid": user.id},
        )
        db.commit()
        raise

    # Re-fetch fresh generation balance for the response
    db.refresh(user)

    actual_gens = result.get("generations_used", body.variations)

    return GenerateResponse(
        type=body.type,
        variations=result["variations"],
        generations_used=actual_gens,
        generations=user.generations,
        generation_time_ms=result["generation_time_ms"],
    )


# ══════════════════════════════════════════════════════════════════════════════
# BILLING ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/billing/subscribe", response_model=CheckoutResponse, tags=["Billing"])
async def subscribe(
    body: CheckoutRequest,
    current_user: User = Depends(get_current_user_jwt),
    db: Session = Depends(get_db),
):
    """Create a Stripe checkout session for a subscription plan."""
    result = create_subscription_checkout(
        plan=body.plan,
        user=current_user,
        db=db,
    )
    return CheckoutResponse(**result)


@app.post("/billing/one-time", response_model=CheckoutResponse, tags=["Billing"])
async def buy_one_time(
    body: OneTimeGenerationsRequest,
    current_user: User = Depends(get_current_user_jwt),
    db: Session = Depends(get_db),
):
    """Create a Stripe checkout session for a one-time generation pack."""
    result = create_one_time_checkout(
        pack=body.tier,
        user=current_user,
        db=db,
    )
    return CheckoutResponse(**result)


@app.post("/billing/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="stripe-signature"),
    db: Session = Depends(get_db),
):
    """
    Stripe sends payment events here automatically.
    This is how the server knows when to grant or revoke access.
    """
    payload = await request.body()
    result  = handle_stripe_webhook(payload, stripe_signature or "", db)
    return JSONResponse(content=result)


@app.get("/billing/status", tags=["Billing"])
async def billing_status(
    current_user: User = Depends(get_current_user_jwt),
    db: Session = Depends(get_db),
):
    """Returns the current user's subscription status and generation balance."""
    from .database import Subscription
    sub = db.query(Subscription).filter(
        Subscription.user_id == current_user.id,
        Subscription.status == "active",
    ).order_by(Subscription.created_at.desc()).first()

    return {
        "plan":                  current_user.plan,
        "status":                sub.status if sub else "free",
        "generations": current_user.generations,
        "monthly_limit":         current_user.monthly_limit,
        "current_period_end":    sub.current_period_end if sub else None,
    }


# ══════════════════════════════════════════════════════════════════════════════
# USAGE ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/usage", response_model=UsageSummary, tags=["Usage"])
async def get_usage(
    current_user: User = Depends(get_current_user_jwt),
    db: Session = Depends(get_db),
):
    """Returns the current user's usage stats for this billing cycle."""
    from sqlalchemy import func
    from .database import Subscription

    sub = db.query(Subscription).filter(
        Subscription.user_id == current_user.id,
        Subscription.status == "active",
    ).order_by(Subscription.created_at.desc()).first()

    period_start = sub.current_period_start.isoformat() if sub and sub.current_period_start else None
    period_end   = sub.current_period_end.isoformat()   if sub and sub.current_period_end   else None

    agg = db.query(
        func.count(UsageRecord.id).label("total_requests"),
        func.sum(UsageRecord.generations_used).label("total_generations"),
    ).filter(UsageRecord.user_id == current_user.id).first()

    total_gens = agg.total_generations or 0
    return UsageSummary(
        total_requests=agg.total_requests or 0,
        total_generations_used=total_gens,
        generations=current_user.generations,
        monthly_limit=current_user.monthly_limit,
        plan=current_user.plan,
        period_start=period_start,
        period_end=period_end,
    )


# ══════════════════════════════════════════════════════════════════════════════
# OWNER-ONLY ADMIN ROUTE
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/revenue", tags=["Admin"])
async def admin_revenue(
    x_admin_secret: Optional[str] = Header(None, alias="x-admin-secret"),
    db: Session = Depends(get_db),
):
    """Owner-only: total revenue stats. Pass your ADMIN_SECRET in the X-Admin-Secret header."""
    if not ADMIN_SECRET or x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    return get_total_revenue(db)

@app.get("/api/admin/stats", tags=["Admin"])
async def admin_stats(
    x_admin_secret: Optional[str] = Header(None, alias="x-admin-secret"),
    db: Session = Depends(get_db),
):
    """Admin dashboard stats."""
    if not ADMIN_SECRET or x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    from sqlalchemy import func
    from .database import RevenueRecord
    
    users = db.query(User).count()
    paying = db.query(User).filter(User.plan != "free").count()
    revenue = db.query(func.sum(RevenueRecord.amount_cents)).filter(RevenueRecord.status == "succeeded").scalar() or 0
    reqs = db.query(func.count(UsageRecord.id)).scalar() or 0
    gens = db.query(func.sum(UsageRecord.generations_used)).scalar() or 0
    
    recent = db.query(User).order_by(User.created_at.desc()).limit(10).all()
    
    return {
        "total_users": users,
        "paying_users": paying,
        "total_revenue_cents": revenue,
        "total_requests": reqs,
        "total_generations": gens,
        "recent_users": [
            {"email": u.email, "plan": u.plan, "created_at": u.created_at.isoformat()}
            for u in recent
        ]
    }

@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_page():
    """Serve the admin dashboard."""
    path = BASE_DIR / "frontend" / "admin.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Admin panel not found")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

@app.post("/auth/request-password-reset", tags=["Auth"])
@limiter.limit("5/minute")
async def request_password_reset(
    request: Request,
    body: RequestPasswordReset,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    from .database import VerificationToken, User
    import secrets
    from datetime import datetime, timedelta
    from .scheduler import _send_password_reset_email

    user = db.query(User).filter(User.email == body.email).first()
    if user:
        token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(hours=1)
        db.add(VerificationToken(token=token, user_id=user.id, token_type="password_reset", expires_at=expires))
        db.commit()
        
        base_url = "https://kopykat-ai.onrender.com"
        background_tasks.add_task(_send_password_reset_email, user.email, token, base_url)
    
    return {"message": "If an account with that email exists, a password reset link has been sent."}

@app.post("/auth/reset-password", tags=["Auth"])
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    body: ResetPasswordSubmit,
    db: Session = Depends(get_db)
):
    from .database import VerificationToken, User
    from .auth import get_password_hash
    from datetime import datetime

    token_record = db.query(VerificationToken).filter(
        VerificationToken.token == body.token,
        VerificationToken.token_type == "password_reset",
        VerificationToken.expires_at > datetime.utcnow()
    ).first()

    if not token_record:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token.")

    user = db.query(User).filter(User.id == token_record.user_id).first()
    if user:
        user.hashed_password = get_password_hash(body.new_password)
        db.delete(token_record)
        db.commit()
        return {"message": "Password successfully reset."}
    
    raise HTTPException(status_code=400, detail="User not found.")

@app.post("/api/integrations", tags=["Integrations"])
@limiter.limit("20/minute")
async def save_integration(
    request: Request,
    body: IntegrationSaveRequest,
    auth: tuple = Depends(get_current_user_apikey),
    db: Session = Depends(get_db)
):
    from .database import UserIntegration
    import json
    import uuid
    user, _ = auth

    existing = db.query(UserIntegration).filter(
        UserIntegration.user_id == user.id,
        UserIntegration.platform == body.platform
    ).first()

    from .auth import encrypt_credentials
    
    enc_creds = encrypt_credentials(json.dumps(body.credentials))
    if existing:
        existing.credentials = enc_creds
        existing.status = "connected"
    else:
        new_int = UserIntegration(
            id=str(uuid.uuid4()),
            user_id=user.id,
            platform=body.platform,
            credentials=enc_creds,
            status="connected"
        )
        db.add(new_int)

    db.commit()
    return {"message": f"{body.platform.capitalize()} integration saved"}

@app.get("/api/integrations", tags=["Integrations"])
async def get_integrations(
    auth: tuple = Depends(get_current_user_apikey),
    db: Session = Depends(get_db)
):
    from .database import UserIntegration
    from .auth import decrypt_credentials
    from .integrations import fetch_metadata
    import json
    
    user, _ = auth
    ints = db.query(UserIntegration).filter(UserIntegration.user_id == user.id).all()
    
    connected = []
    metadata_map = {}
    
    for i in ints:
        connected.append(i.platform)
        try:
            creds = json.loads(decrypt_credentials(i.credentials))
            opts = fetch_metadata(i.platform, creds)
            if opts:
                metadata_map[i.platform] = opts
        except:
            pass
            
    return {"connected": connected, "metadata": metadata_map}

@app.post("/api/push", tags=["Integrations"])
@limiter.limit("10/minute")
async def push_content(
    request: Request,
    body: PushRequest,
    background_tasks: BackgroundTasks,
    auth: tuple = Depends(get_current_user_apikey),
    db: Session = Depends(get_db)
):
    from .database import UserIntegration, PushJob
    from .auth import decrypt_credentials
    import json
    import uuid
    user, _ = auth

    integration = db.query(UserIntegration).filter(
        UserIntegration.user_id == user.id,
        UserIntegration.platform == body.platform
    ).first()

    if not integration:
        raise HTTPException(status_code=400, detail=f"No {body.platform} integration configured.")

    try:
        decrypted = decrypt_credentials(integration.credentials)
        creds = json.loads(decrypted)
    except Exception:
        integration.status = "invalid_credentials"
        db.commit()
        raise HTTPException(status_code=400, detail="Integration credentials invalid or corrupted. Please reconnect.")

    job_id = str(uuid.uuid4())
    
    # Create the job in the DB
    job = PushJob(id=job_id, user_id=user.id, platform=body.platform, status="pending")
    db.add(job)
    db.commit()

    from .integrations import background_push
    
    # Run the high-latency push in the background
    background_tasks.add_task(background_push, body.platform, creds, body.title, body.content, body.metadata, integration.id, job_id)

    return JSONResponse(status_code=202, content={"message": "Push accepted", "job_id": job_id})

@app.get("/api/push/status/{job_id}", tags=["Integrations"])
async def get_push_status(
    job_id: str,
    auth: tuple = Depends(get_current_user_apikey),
    db: Session = Depends(get_db)
):
    from .database import PushJob
    user, _ = auth
    job = db.query(PushJob).filter(PushJob.id == job_id, PushJob.user_id == user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Push job not found.")
    
    return {"status": job.status, "details": job.details}




@app.post("/api/public/demo", tags=["Public"])
@limiter.limit("2/day")
async def api_public_demo(
    request: Request,
    body: CampaignGenerateRequest,
    db: Session = Depends(get_db)
):
    from .campaigns import generate_demo_campaign
    try:
        campaign_data = generate_demo_campaign(body.keyword, body.product_desc)
        return {"assets": campaign_data}
    except Exception as e:
        logger.error(f"Public demo failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Demo generation failed due to an internal error.")

@app.post("/api/campaign/generate", tags=["Campaigns"])
@limiter.limit("5/minute")
async def api_campaign_generate(
    request: Request,
    body: CampaignGenerateRequest,
    auth: tuple = Depends(get_current_user_apikey),
    db: Session = Depends(get_db)
):
    from .database import Campaign, UsageRecord
    from .campaigns import generate_omni_campaign
    import uuid
    import json
    
    user, _ = auth
    
    # 1. Atomic deduction (prevents concurrency bypass)
    rows_updated = db.execute(
        text(
            "UPDATE users SET generations = generations - 1 "
            "WHERE id = :uid AND generations >= 1"
        ),
        {"uid": user.id}
    ).rowcount

    if rows_updated == 0:
        raise HTTPException(
            status_code=402, 
            detail="Insufficient campaigns remaining. Please upgrade your plan."
        )

    try:
        campaign_data = generate_omni_campaign(body.keyword, body.product_desc)
        
        # Save to DB
        campaign_id = str(uuid.uuid4())
        name = f"Campaign: {body.keyword.title()}"
        camp = Campaign(
            id=campaign_id,
            user_id=user.id,
            name=name,
            assets=json.dumps(campaign_data)
        )
        db.add(camp)
        
        # Log usage record
        usage = UsageRecord(
            user_id=user.id,
            type="omni_campaign",
            context=f"Keyword: {body.keyword}",
            cost=1
        )
        db.add(usage)
        
        db.commit() # Commits both the deduction and the new records
        
        return {"id": campaign_id, "name": name, "assets": campaign_data}
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Campaign generation failed for user {user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Generation failed due to an internal error. Your balance was not charged.")

@app.post("/api/campaign/push", tags=["Campaigns"])
@limiter.limit("5/minute")
async def api_campaign_push(
    request: Request,
    body: CampaignPushRequest,
    background_tasks: BackgroundTasks,
    auth: tuple = Depends(get_current_user_apikey),
    db: Session = Depends(get_db)
):
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
    job_ids = []
    
    for asset_type, dest_info in body.destinations.items():
        platform = dest_info.get("platform")
        meta = dest_info.get("metadata", {})
        
        if not platform:
            continue
            
        integration = db.query(UserIntegration).filter(
            UserIntegration.user_id == user.id,
            UserIntegration.platform == platform
        ).first()
        
        if not integration:
            continue
            
        try:
            creds = json.loads(decrypt_credentials(integration.credentials))
        except:
            continue
            
        title = ""
        content = ""
        if asset_type == "blog" and "blog_post" in assets:
            title = assets["blog_post"]["title"]
            content = assets["blog_post"]["content"]
        elif asset_type == "email" and "email_drip" in assets:
            if len(assets["email_drip"]) > 0:
                title = assets["email_drip"][0]["subject"]
                content = assets["email_drip"][0]["body"]
        else:
            continue
            
        if not content:
            continue
            
        job_id = str(uuid.uuid4())
        job = PushJob(id=job_id, user_id=user.id, platform=platform, status="pending")
        db.add(job)
        job_ids.append(job_id)
        
        background_tasks.add_task(background_push, platform, creds, title, content, meta, integration.id, job_id)
        
    db.commit()
    return JSONResponse(status_code=202, content={"message": "Omni-Push accepted", "job_ids": job_ids})
