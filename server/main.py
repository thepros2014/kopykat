"""KopyKat FastAPI application entry point."""
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import bleach
from fastapi import FastAPI, Depends, HTTPException, Request, Header, BackgroundTasks, status, File, UploadFile
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
from .models import *
from .auth import register_user, authenticate_user, create_access_token, create_user_api_key, revoke_api_key, get_current_user_jwt, get_current_user_apikey
from .ai_engine import generate_copy
from .billing import create_subscription_checkout, create_one_time_checkout, handle_stripe_webhook, get_total_revenue, PLANS, ONE_TIME_GENERATIONS
from .marketing import generate_seo_post

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)
APP_VERSION = "1.0.1"
BASE_DIR = Path(__file__).parent.parent
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
limiter = Limiter(key_func=get_remote_address)

import sentry_sdk
SENTRY_DSN = os.environ.get("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=1.0, profiles_sample_rate=1.0)

app = FastAPI(title="KopyKat", description="Instant AI-powered marketing copy. Automated. Always on.", version=APP_VERSION, docs_url="/api/docs", redoc_url="/api/redoc")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
_raw_origins = os.getenv("ALLOWED_ORIGINS", "https://kopykat.onrender.com")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=True, allow_methods=["GET", "POST", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "X-Admin-Secret"])
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])
_ALLOWED_TAGS = ["p", "h2", "h3", "h4", "ul", "ol", "li", "strong", "em", "b", "i", "a", "br", "blockquote"]
_ALLOWED_ATTRS = {"a": ["href", "title", "rel"]}
def sanitize_html(raw: str) -> str:
    return bleach.clean(raw, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True, strip_comments=True)

@app.on_event("startup")
async def startup():
    logger.info("KopyKat starting up")
    init_db()
    logger.info("Database initialized")
    logger.info("KopyKat v%s is live", APP_VERSION)

@app.on_event("shutdown")
async def shutdown():
    logger.info("KopyKat shut down gracefully")

frontend_dir = BASE_DIR / "frontend"
if (frontend_dir / "static").exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir / "static")), name="static")

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def landing_page():
    index = frontend_dir / "index.html"
    return HTMLResponse(index.read_text(encoding="utf-8")) if index.exists() else HTMLResponse("<h1>KopyKat — Loading...</h1>")

@app.get("/manifest.json", include_in_schema=False)
async def get_manifest(): return FileResponse(frontend_dir / "manifest.json")
@app.get("/sw.js", include_in_schema=False)
async def get_sw(): return FileResponse(frontend_dir / "sw.js")
@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_page():
    dash = frontend_dir / "dashboard.html"
    return HTMLResponse(dash.read_text(encoding="utf-8")) if dash.exists() else HTMLResponse("<h1>Dashboard — Loading...</h1>")

@app.get("/admin/trigger-seo", include_in_schema=False)
async def trigger_seo(background_tasks: BackgroundTasks, x_admin_secret: Optional[str] = Header(None, alias="x-admin-secret")):
    if not ADMIN_SECRET or x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    background_tasks.add_task(generate_seo_post)
    return {"status": "ok", "message": "SEO blog generation started in background."}

@app.get("/blog", response_class=HTMLResponse, include_in_schema=False)
async def blog_index(db: Session = Depends(get_db)):
    posts = db.query(BlogPost).filter(BlogPost.published == True).order_by(BlogPost.created_at.desc()).all()
    items = "".join(f'<article><h2>{bleach.clean(p.title)}</h2><p>{bleach.clean(p.meta_desc or "")}</p></article>' for p in posts)
    return HTMLResponse(f"<html><body><h1>KopyKat Blog</h1>{items}</body></html>")
