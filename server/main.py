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
from fastapi import (FastAPI, Depends, HTTPException, Request, Header, BackgroundTasks, status, File, UploadFile)
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
from .models import (RequestPasswordReset, ResetPasswordSubmit, IntegrationSaveRequest, PushRequest, CampaignGenerateRequest, CampaignPushRequest, UserRegister, UserLogin, TokenResponse, UserProfile, APIKeyCreate, APIKeyResponse, APIKeyCreated, GenerateRequest, GenerateResponse, CheckoutRequest, OneTimeGenerationsRequest, CheckoutResponse, SubscriptionStatus, UsageSummary, HealthResponse)
from .auth import register_user, authenticate_user, create_access_token, create_user_api_key, revoke_api_key, get_current_user_jwt, get_current_user_apikey
from .ai_engine import generate_copy
from .billing import create_subscription_checkout, create_one_time_checkout, handle_stripe_webhook, get_total_revenue, PLANS, ONE_TIME_GENERATIONS
from .marketing import generate_seo_post

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)
APP_VERSION="1.0.1"; BASE_DIR=Path(__file__).parent.parent; ADMIN_SECRET=os.getenv("ADMIN_SECRET","")
limiter=Limiter(key_func=get_remote_address)
import sentry_sdk
if os.environ.get("SENTRY_DSN"): sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], traces_sample_rate=1.0, profiles_sample_rate=1.0)
app=FastAPI(title="KopyKat",description="Instant AI-powered marketing copy. Automated. Always on.",version=APP_VERSION,docs_url="/api/docs",redoc_url="/api/redoc")
app.state.limiter=limiter; app.add_exception_handler(RateLimitExceeded,_rate_limit_exceeded_handler)
ALLOWED_ORIGINS=[o.strip() for o in os.getenv("ALLOWED_ORIGINS","https://kopykat.onrender.com").split(",") if o.strip()]
app.add_middleware(CORSMiddleware,allow_origins=ALLOWED_ORIGINS,allow_credentials=True,allow_methods=["GET","POST","DELETE","OPTIONS"],allow_headers=["Authorization","Content-Type","X-Admin-Secret"])
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
app.add_middleware(ProxyHeadersMiddleware,trusted_hosts=["*"])
_ALLOWED_TAGS=["p","h2","h3","h4","ul","ol","li","strong","em","b","i","a","br","blockquote"]; _ALLOWED_ATTRS={"a":["href","title","rel"]}
def sanitize_html(raw:str)->str: return bleach.clean(raw,tags=_ALLOWED_TAGS,attributes=_ALLOWED_ATTRS,strip=True,strip_comments=True)

@app.on_event("startup")
async def startup(): logger.info("KopyKat starting up"); init_db(); logger.info("Database initialized"); logger.info("KopyKat v%s is live",APP_VERSION)
@app.on_event("shutdown")
async def shutdown(): logger.info("KopyKat shut down gracefully")
frontend_dir=BASE_DIR/"frontend"
if (frontend_dir/"static").exists(): app.mount("/static",StaticFiles(directory=str(frontend_dir/"static")),name="static")

@app.get("/",response_class=HTMLResponse,include_in_schema=False)
async def landing_page():
    index=frontend_dir/"index.html"; return HTMLResponse(index.read_text(encoding="utf-8")) if index.exists() else HTMLResponse("<h1>KopyKat — Loading...</h1>")
@app.get("/manifest.json",include_in_schema=False)
async def get_manifest(): return FileResponse(frontend_dir/"manifest.json")
@app.get("/sw.js",include_in_schema=False)
async def get_sw(): return FileResponse(frontend_dir/"sw.js")
@app.get("/dashboard",response_class=HTMLResponse,include_in_schema=False)
async def dashboard_page():
    dash=frontend_dir/"dashboard.html"; return HTMLResponse(dash.read_text(encoding="utf-8")) if dash.exists() else HTMLResponse("<h1>Dashboard — Loading...</h1>")
@app.get("/admin/trigger-seo",include_in_schema=False)
async def trigger_seo(background_tasks:BackgroundTasks,x_admin_secret:Optional[str]=Header(None,alias="x-admin-secret")):
    if not ADMIN_SECRET or x_admin_secret!=ADMIN_SECRET: raise HTTPException(status_code=401,detail="Unauthorized")
    background_tasks.add_task(generate_seo_post); return {"status":"ok","message":"SEO blog generation started in background."}
@app.get("/blog",response_class=HTMLResponse,include_in_schema=False)
async def blog_index(db:Session=Depends(get_db)):
    posts=db.query(BlogPost).filter(BlogPost.published==True).order_by(BlogPost.created_at.desc()).all(); template_path=frontend_dir/"blog.html"
    if not template_path.exists(): return HTMLResponse("<h1>Blog setup pending...</h1>")
    template=template_path.read_text(encoding="utf-8"); items="".join(f'<div class="card"><div>{p.created_at.strftime("%B %d, %Y")}</div><h2><a href="/blog/{p.slug}">{bleach.clean(p.title)}</a></h2><p>{bleach.clean(p.meta_desc or "")}</p></div>' for p in posts)
    return HTMLResponse(template.replace("<!-- POSTS -->",items or "<p>No posts yet. The AI is writing the first one!</p>"))
@app.get("/blog/{slug}",response_class=HTMLResponse,include_in_schema=False)
async def blog_post(slug:str,db:Session=Depends(get_db)):
    post=db.query(BlogPost).filter(BlogPost.slug==slug,BlogPost.published==True).first()
    if not post: raise HTTPException(status_code=404,detail="Post not found")
    path=frontend_dir/"post.html"
    if not path.exists(): return HTMLResponse("<h1>Post layout pending...</h1>")
    html=path.read_text(encoding="utf-8").replace("{{title}}",bleach.clean(post.title)).replace("{{content}}",sanitize_html(post.content)).replace("{{meta_desc}}",bleach.clean(post.meta_desc or "")).replace("{{date}}",post.created_at.strftime("%B %d, %Y")); return HTMLResponse(html)
@app.get("/health",response_model=HealthResponse,tags=["System"])
async def health_check(): return HealthResponse(status="ok",version=APP_VERSION,timestamp=datetime.utcnow())
@app.get("/api/plans",tags=["Billing"])
async def list_plans(): return {"subscriptions":{k:{"name":v["name"],"price_usd":v["price_usd"],"monthly_generations":v["monthly_generations"],"features":v["features"]} for k,v in PLANS.items()},"one_time_generations":{k:{"name":v["name"],"price_usd":v["price_usd"],"generations":v["generations"]} for k,v in ONE_TIME_GENERATIONS.items()}}

@app.post("/auth/register",response_model=TokenResponse,tags=["Auth"])
@limiter.limit("5/minute")
async def register(request:Request,body:UserRegister,background_tasks:BackgroundTasks,db:Session=Depends(get_db)):
    user=register_user(body.email,body.password,body.full_name,db); from .scheduler import _send_email; background_tasks.add_task(_send_email,"Welcome to KopyKat 🚀",f"Hi {body.full_name or 'there'},<br><br>Welcome to KopyKat! Your account is loaded with 5 free generations.",user.email); return TokenResponse(access_token=create_access_token(user.id,user.email),plan=user.plan,generations=user.generations)
@app.post("/auth/login",response_model=TokenResponse,tags=["Auth"])
@limiter.limit("10/minute")
async def login(request:Request,body:UserLogin,db:Session=Depends(get_db)):
    user=authenticate_user(body.email,body.password,db)
    if not user: raise HTTPException(status_code=401,detail="Invalid email or password")
    return TokenResponse(access_token=create_access_token(user.id,user.email),plan=user.plan,generations=user.generations)
@app.get("/auth/me",response_model=UserProfile,tags=["Auth"])
async def get_profile(current_user:User=Depends(get_current_user_jwt)): return current_user
@app.post("/api/keys",response_model=APIKeyCreated,tags=["API Keys"])
async def create_api_key(body:APIKeyCreate,current_user:User=Depends(get_current_user_jwt),db:Session=Depends(get_db)):
    raw,api=create_user_api_key(current_user,body.name,db); return APIKeyCreated(id=api.id,key_prefix=api.key_prefix,name=api.name,is_active=api.is_active,last_used=api.last_used,requests_today=api.requests_today,created_at=api.created_at,raw_key=raw)
@app.get("/api/keys",response_model=list[APIKeyResponse],tags=["API Keys"])
async def list_api_keys(current_user:User=Depends(get_current_user_jwt),db:Session=Depends(get_db)): return db.query(APIKey).filter(APIKey.user_id==current_user.id,APIKey.is_active==True).all()
@app.delete("/api/keys/{key_id}",tags=["API Keys"])
async def delete_api_key(key_id:str,current_user:User=Depends(get_current_user_jwt),db:Session=Depends(get_db)):
    if not revoke_api_key(key_id,current_user,db): raise HTTPException(status_code=404,detail="Key not found")
    return {"status":"revoked"}
@app.post("/api/generate",response_model=GenerateResponse,tags=["Generate"])
@limiter.limit("60/minute")
async def generate(request:Request,body:GenerateRequest,auth:tuple=Depends(get_current_user_apikey),db:Session=Depends(get_db)):
    user,api_key=auth; cost=body.variations; updated=db.execute(text("UPDATE users SET generations = generations - :cost WHERE id = :uid AND generations >= :cost"),{"cost":cost,"uid":user.id}).rowcount; db.commit()
    if updated==0: raise HTTPException(status_code=402,detail="No generations remaining. Upgrade your plan or buy a generation pack at /dashboard")
    try: result=await generate_copy(copy_type=body.type,context=body.context,tone=body.tone or "professional",variations=body.variations,max_tokens=body.max_words,user_id=user.id,db=db)
    except Exception: db.execute(text("UPDATE users SET generations = generations + :cost WHERE id = :uid"),{"cost":cost,"uid":user.id}); db.commit(); raise
    db.refresh(user); actual=result.get("generations_used",body.variations); return GenerateResponse(type=body.type,variations=result["variations"],generations_used=actual,generations=user.generations,generation_time_ms=result["generation_time_ms"])
@app.post("/billing/subscribe",response_model=CheckoutResponse,tags=["Billing"])
async def subscribe(body:CheckoutRequest,current_user:User=Depends(get_current_user_jwt),db:Session=Depends(get_db)): return CheckoutResponse(**create_subscription_checkout(plan=body.plan,user=current_user,db=db))
@app.post("/billing/one-time",response_model=CheckoutResponse,tags=["Billing"])
async def buy_one_time(body:OneTimeGenerationsRequest,current_user:User=Depends(get_current_user_jwt),db:Session=Depends(get_db)): return CheckoutResponse(**create_one_time_checkout(pack=body.tier,user=current_user,db=db))
@app.post("/billing/webhook",include_in_schema=False)
async def stripe_webhook(request:Request,stripe_signature:Optional[str]=Header(None,alias="stripe-signature"),db:Session=Depends(get_db)): return JSONResponse(content=handle_stripe_webhook(await request.body(),stripe_signature or "",db))
@app.get("/billing/status",tags=["Billing"])
async def billing_status(current_user:User=Depends(get_current_user_jwt),db:Session=Depends(get_db)):
    from .database import Subscription; sub=db.query(Subscription).filter(Subscription.user_id==current_user.id,Subscription.status=="active").order_by(Subscription.created_at.desc()).first(); return {"plan":current_user.plan,"status":sub.status if sub else "free","generations":current_user.generations,"monthly_limit":current_user.monthly_limit,"current_period_end":sub.current_period_end if sub else None}
@app.get("/api/usage",response_model=UsageSummary,tags=["Usage"])
async def get_usage(current_user:User=Depends(get_current_user_jwt),db:Session=Depends(get_db)):
    from sqlalchemy import func; from .database import Subscription; sub=db.query(Subscription).filter(Subscription.user_id==current_user.id,Subscription.status=="active").order_by(Subscription.created_at.desc()).first(); agg=db.query(func.count(UsageRecord.id).label("total_requests"),func.sum(UsageRecord.generations_used).label("total_generations")).filter(UsageRecord.user_id==current_user.id).first(); return UsageSummary(total_requests=agg.total_requests or 0,total_generations_used=agg.total_generations or 0,generations=current_user.generations,monthly_limit=current_user.monthly_limit,plan=current_user.plan,period_start=sub.current_period_start.isoformat() if sub and sub.current_period_start else None,period_end=sub.current_period_end.isoformat() if sub and sub.current_period_end else None)
@app.get("/admin/revenue",tags=["Admin"])
async def admin_revenue(x_admin_secret:Optional[str]=Header(None,alias="x-admin-secret"),db:Session=Depends(get_db)):
    if not ADMIN_SECRET or x_admin_secret!=ADMIN_SECRET: raise HTTPException(status_code=403,detail="Forbidden")
    return get_total_revenue(db)
@app.get("/api/admin/stats",tags=["Admin"])
async def admin_stats(x_admin_secret:Optional[str]=Header(None,alias="x-admin-secret"),db:Session=Depends(get_db)):
    if not ADMIN_SECRET or x_admin_secret!=ADMIN_SECRET: raise HTTPException(status_code=401,detail="Unauthorized")
    from sqlalchemy import func; from .database import RevenueRecord; users=db.query(User).count(); paying=db.query(User).filter(User.plan!="free").count(); revenue=db.query(func.sum(RevenueRecord.amount_cents)).filter(RevenueRecord.status=="succeeded").scalar() or 0; reqs=db.query(func.count(UsageRecord.id)).scalar() or 0; gens=db.query(func.sum(UsageRecord.generations_used)).scalar() or 0; recent=db.query(User).order_by(User.created_at.desc()).limit(10).all(); return {"total_users":users,"paying_users":paying,"total_revenue_cents":revenue,"total_requests":reqs,"total_generations":gens,"recent_users":[{"email":u.email,"plan":u.plan,"created_at":u.created_at.isoformat()} for u in recent]}
@app.get("/admin",response_class=HTMLResponse,include_in_schema=False)
async def admin_page():
    path=BASE_DIR/"frontend"/"admin.html"
    if not path.exists(): raise HTTPException(status_code=404,detail="Admin panel not found")
    return path.read_text(encoding="utf-8")
@app.post("/auth/request-password-reset",tags=["Auth"])
@limiter.limit("5/minute")
async def request_password_reset(request:Request,body:RequestPasswordReset,background_tasks:BackgroundTasks,db:Session=Depends(get_db)):
    from .database import VerificationToken,User; import secrets; from datetime import timedelta; from .scheduler import _send_password_reset_email; user=db.query(User).filter(User.email==body.email).first()
    if user:
        token=secrets.token_urlsafe(32); db.add(VerificationToken(token=token,user_id=user.id,token_type="password_reset",expires_at=datetime.utcnow()+timedelta(hours=1))); db.commit(); background_tasks.add_task(_send_password_reset_email,user.email,token,os.getenv("PUBLIC_APP_URL","https://kopykat.onrender.com"))
    return {"message":"If an account with that email exists, a password reset link has been sent."}
@app.post("/auth/reset-password",tags=["Auth"])
@limiter.limit("5/minute")
async def reset_password(request:Request,body:ResetPasswordSubmit,db:Session=Depends(get_db)):
    from .database import VerificationToken,User; from .auth import hash_password; token_record=db.query(VerificationToken).filter(VerificationToken.token==body.token,VerificationToken.token_type=="password_reset",VerificationToken.expires_at>datetime.utcnow()).first()
    if not token_record: raise HTTPException(status_code=400,detail="Invalid or expired reset token.")
    user=db.query(User).filter(User.id==token_record.user_id).first()
    if not user: raise HTTPException(status_code=400,detail="User not found.")
    user.hashed_password=hash_password(body.new_password); db.delete(token_record); db.commit(); return {"message":"Password successfully reset."}

# Integration/campaign routes remain in their dedicated modules and are exposed below.
@app.post("/api/integrations",tags=["Integrations"])
async def save_integration(request:Request,body:IntegrationSaveRequest,auth:tuple=Depends(get_current_user_apikey),db:Session=Depends(get_db)):
    from .database import UserIntegration; from .auth import encrypt_credentials; import json,uuid; user,_=auth; existing=db.query(UserIntegration).filter(UserIntegration.user_id==user.id,UserIntegration.platform==body.platform).first(); enc=encrypt_credentials(json.dumps(body.credentials));
    if existing: existing.credentials=enc; existing.status="connected"
    else: db.add(UserIntegration(id=str(uuid.uuid4()),user_id=user.id,platform=body.platform,credentials=enc,status="connected"))
    db.commit(); return {"message":f"{body.platform.capitalize()} integration saved"}
@app.get("/api/integrations",tags=["Integrations"])
async def get_integrations(auth:tuple=Depends(get_current_user_apikey),db:Session=Depends(get_db)):
    from .database import UserIntegration; from .auth import decrypt_credentials; from .integrations import fetch_metadata; import json; user,_=auth; ints=db.query(UserIntegration).filter(UserIntegration.user_id==user.id).all(); connected=[]; metadata={}
    for i in ints:
        connected.append(i.platform)
        try:
            opts=fetch_metadata(i.platform,json.loads(decrypt_credentials(i.credentials)))
            if opts: metadata[i.platform]=opts
        except Exception: pass
    return {"connected":connected,"metadata":metadata}
@app.post("/api/push",tags=["Integrations"])
async def push_content(request:Request,body:PushRequest,background_tasks:BackgroundTasks,auth:tuple=Depends(get_current_user_apikey),db:Session=Depends(get_db)):
    from .database import UserIntegration,PushJob; from .auth import decrypt_credentials; import json,uuid; user,_=auth; integration=db.query(UserIntegration).filter(UserIntegration.user_id==user.id,UserIntegration.platform==body.platform).first()
    if not integration: raise HTTPException(status_code=400,detail=f"No {body.platform} integration configured.")
    try: creds=json.loads(decrypt_credentials(integration.credentials))
    except Exception: integration.status="invalid_credentials"; db.commit(); raise HTTPException(status_code=400,detail="Integration credentials invalid or corrupted. Please reconnect.")
    job_id=str(uuid.uuid4()); db.add(PushJob(id=job_id,user_id=user.id,platform=body.platform,status="pending")); db.commit(); from .integrations import background_push; background_tasks.add_task(background_push,body.platform,creds,body.title,body.content,body.metadata,integration.id,job_id); return JSONResponse(status_code=202,content={"message":"Push accepted","job_id":job_id})
@app.get("/api/push/status/{job_id}",tags=["Integrations"])
async def get_push_status(job_id:str,auth:tuple=Depends(get_current_user_apikey),db:Session=Depends(get_db)):
    from .database import PushJob; user,_=auth; job=db.query(PushJob).filter(PushJob.id==job_id,PushJob.user_id==user.id).first()
    if not job: raise HTTPException(status_code=404,detail="Push job not found.")
    return {"status":job.status,"details":job.details}
@app.post("/api/public/demo",tags=["Public"])
@limiter.limit("2/day")
async def api_public_demo(request:Request,body:CampaignGenerateRequest,db:Session=Depends(get_db)):
    from .campaigns import generate_demo_campaign
    try: return {"assets":generate_demo_campaign(body.keyword,body.product_desc)}
    except Exception as e: logger.error("Public demo failed: %s",e,exc_info=True); raise HTTPException(status_code=500,detail="Demo generation failed due to an internal error.")
@app.post("/api/catalog/parse-csv",tags=["Campaigns"])
async def api_parse_csv(request:Request,file:UploadFile=File(...),auth:tuple=Depends(get_current_user_apikey)):
    import csv,io; from .ai_engine import analyze_csv_mapping; content=await file.read()
    try: text_content=content.decode("utf-8-sig")
    except UnicodeDecodeError: raise HTTPException(status_code=400,detail="CSV must be UTF-8 encoded.")
    rows=list(csv.reader(io.StringIO(text_content)))
    if len(rows)<2: raise HTTPException(status_code=400,detail="CSV is empty or missing headers.")
    headers=rows[0]; mapping=await analyze_csv_mapping(headers,rows[1]); name_col=mapping.get("name_col",""); desc_col=mapping.get("desc_col","")
    if not name_col: raise HTTPException(status_code=400,detail="AI could not identify a Product Name column.")
    try: name_idx=headers.index(name_col)
    except ValueError: raise HTTPException(status_code=400,detail=f"AI returned invalid name column: {name_col}")
    desc_idx=headers.index(desc_col) if desc_col in headers else -1; results=[]
    for r in rows[1:]:
        if len(r)<=name_idx or not r[name_idx].strip(): continue
        results.append({"name":r[name_idx],"desc":r[desc_idx] if desc_idx!=-1 and len(r)>desc_idx else ""})
    return {"items":results[:100],"mapping_used":mapping}
@app.post("/api/campaign/generate",tags=["Campaigns"])
@limiter.limit("5/minute")
async def api_campaign_generate(request:Request,body:CampaignGenerateRequest,auth:tuple=Depends(get_current_user_apikey),db:Session=Depends(get_db)):
    from .database import Campaign; from .campaigns import generate_omni_campaign; import uuid,json; user,_=auth; updated=db.execute(text("UPDATE users SET generations = generations - 1 WHERE id = :uid AND generations >= 1"),{"uid":user.id}).rowcount
    if updated==0: raise HTTPException(status_code=402,detail="Insufficient campaigns remaining. Please upgrade your plan.")
    try:
        data=generate_omni_campaign(body.keyword,body.product_desc); cid=str(uuid.uuid4()); name=f"Campaign: {body.keyword.title()}"; db.add(Campaign(id=cid,user_id=user.id,name=name,assets=json.dumps(data))); db.commit(); return {"id":cid,"name":name,"assets":data}
    except ValueError as e: db.rollback(); raise HTTPException(status_code=400,detail=str(e))
    except Exception: db.rollback(); raise HTTPException(status_code=500,detail="Generation failed due to an internal error. Your balance was not charged.")
@app.post("/api/campaign/push",tags=["Campaigns"])
@limiter.limit("5/minute")
async def api_campaign_push(request:Request,body:CampaignPushRequest,background_tasks:BackgroundTasks,auth:tuple=Depends(get_current_user_apikey),db:Session=Depends(get_db)):
    from .database import Campaign,UserIntegration,PushJob; from .auth import decrypt_credentials; from .integrations import background_push; import json,uuid; user,_=auth; camp=db.query(Campaign).filter(Campaign.id==body.campaign_id,Campaign.user_id==user.id).first()
    if not camp: raise HTTPException(status_code=404,detail="Campaign not found")
    assets=json.loads(camp.assets); jobs=[]
    for asset_type,dest in body.destinations.items():
        platform=dest.get("platform"); meta=dest.get("metadata",{}); integration=db.query(UserIntegration).filter(UserIntegration.user_id==user.id,UserIntegration.platform==platform).first() if platform else None
        if not integration: continue
        try: creds=json.loads(decrypt_credentials(integration.credentials))
        except Exception: continue
        if asset_type=="blog" and "blog_post" in assets: title=assets["blog_post"]["title"]; content=assets["blog_post"]["content"]
        elif asset_type=="email" and assets.get("email_drip"): title=assets["email_drip"][0]["subject"]; content=assets["email_drip"][0]["body"]
        else: continue
        if not content: continue
        jid=str(uuid.uuid4()); db.add(PushJob(id=jid,user_id=user.id,platform=platform,status="pending")); jobs.append(jid); background_tasks.add_task(background_push,platform,creds,title,content,meta,integration.id,jid)
    db.commit(); return JSONResponse(status_code=202,content={"message":"Omni-Push accepted","job_ids":jobs})
