"""
marketing.py — The fully automated marketing engine for KopyKat.
Contains the SEO Blog Engine, Email Drip Bot, and Social Opportunity Scout.
"""

import os
import re
import uuid
import json
import logging
import random
from datetime import datetime
from typing import Optional

import httpx
import bleach
from sqlalchemy.orm import Session

from .database import SessionLocal, BlogPost, User, DripLog, OpportunityLog
from .gemini_client import generate_content_async
from .openai_client import generate_text_async
from .scheduler import _send_email

logger = logging.getLogger(__name__)

# --- 1. SEO Blog Engine ---

KEYWORDS = [
    "AI copywriting for ecommerce", 
    "How to write product descriptions with AI",
    "Best AI tools for marketing agencies", 
    "Automate social media copy",
    "AI email sequence generator", 
    "Write better Facebook ads with AI",
    "Copywriting tips for startups",
    "How to increase conversion rates with AI",
    "AI landing page generator",
    "Amazon product listing optimization AI",
    "Shopify SEO product description writer",
    "Etsy tags and title generator AI",
    "TikTok shop viral script generator",
    "Multi-channel inventory and catalog syndication"
]


EMOJI_PATTERN = re.compile(
    r"[\U0001F600-\U0001F64F"
    r"\U0001F300-\U0001F5FF"
    r"\U0001F680-\U0001F6FF"
    r"\U0001F1E0-\U0001F1FF"
    r"\U0001F900-\U0001F9FF"
    r"\U0001FA70-\U0001FAFF"
    r"\U00002702-\U000027B0"
    r"\U000024C2-\U0001F251"
    r"\U00002600-\U000026FF"
    r"\U00002B50"
    r"\U0000FE0F"
    r"\ufffd"
    r"]+",
    flags=re.UNICODE
)

def _strip_emojis(text: str) -> str:
    if not isinstance(text, str):
        return text
    return EMOJI_PATTERN.sub("", text).strip()


def _clean_slug(raw_slug: str) -> str:
    cleaned = re.sub(r'[^a-z0-9\-]+', '', raw_slug.lower().replace(' ', '-'))
    cleaned = re.sub(r'-+', '-', cleaned).strip('-')
    return cleaned or "kopykat-guide"


def _resolve_unique_slug(db: Session, base_slug: str) -> str:
    slug = base_slug
    counter = 1
    while db.query(BlogPost).filter(BlogPost.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


def _ai_provider_order() -> list[str]:
    preferred = os.environ.get("AI_PROVIDER", "openai").strip().lower()
    if preferred not in {"gemini", "openai"}:
        preferred = "openai"
    return [preferred, "openai" if preferred == "gemini" else "gemini"]


async def _generate_marketing_text(
    prompt: str,
    *,
    json_mode: bool = False,
    max_output_tokens: int = 1800,
) -> str:
    """Use the configured provider for scheduled drafts without test egress."""

    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    testing = os.environ.get("ENVIRONMENT", "").strip().lower() in {"test", "testing"}

    for provider in _ai_provider_order():
        try:
            if provider == "gemini" and gemini_key:
                response = await generate_content_async(
                    api_key=gemini_key,
                    model=os.environ.get("GEMINI_MODEL", "gemini-flash-latest"),
                    contents=prompt,
                )
                return (getattr(response, "text", "") or "").strip()
            if provider == "openai" and openai_key and not testing:
                text, _ = await generate_text_async(
                    api_key=openai_key,
                    model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                    input_value=prompt,
                    max_output_tokens=max_output_tokens,
                    json_mode=json_mode,
                )
                return text.strip()
        except Exception:
            logger.warning("Scheduled marketing provider failed: %s", provider, exc_info=True)
            continue
    return ""


async def generate_seo_post(db: Optional[Session] = None, keyword: Optional[str] = None) -> Optional[BlogPost]:
    """Generates and publishes an SEO-optimized blog post."""
    own_db = False
    if db is None:
        db = SessionLocal()
        own_db = True
    try:
        if not keyword:
            keyword = random.choice(KEYWORDS)
        keyword = _strip_emojis(keyword) or "AI Ecommerce Guide"
        logger.info("Starting SEO blog generation for: %s", keyword)

        if not os.environ.get('GEMINI_API_KEY', '').strip() and not os.environ.get('OPENAI_API_KEY', '').strip():
            # Deterministic fallback when API key is unconfigured
            slug_base = _clean_slug(keyword)
            slug = _resolve_unique_slug(db, slug_base)
            post = BlogPost(
                id=str(uuid.uuid4()),
                title=f"The Complete Guide to {keyword}",
                slug=slug,
                keyword=keyword,
                meta_desc=f"Learn how to master {keyword} with automated AI workflows and proven frameworks."[:160],
                content=f"<h2>Mastering {keyword}</h2><p>In modern e-commerce, speed and conversion matter...</p>",
                word_count=250,
                published=True,
                created_at=datetime.utcnow()
            )
            db.add(post)
            db.commit()
            return post

        prompt = f"""Write an SEO-optimized blog post about '{keyword}'.
        Output strictly as a JSON object with these exact keys:
        - "title": a catchy SEO title
        - "slug": url-friendly-slug-of-title
        - "meta_desc": 150 char meta description
        - "content": the full blog post in HTML format (using <h2>, <h3>, <p>, <ul>). Include a subtle pitch for KopyKat at the end. Do not include markdown wrappers around the HTML.
        
        Return ONLY valid JSON.
        """
        text = await _generate_marketing_text(prompt, json_mode=True, max_output_tokens=1800)
        if not text:
            raise RuntimeError("No configured marketing AI provider returned content")
        if text.startswith('```json'): text = text[7:]
        if text.endswith('```'): text = text[:-3]
        text = text.strip()

        data = json.loads(text)

        raw_slug = data.get("slug") or data.get("title") or keyword
        slug_base = _clean_slug(raw_slug)
        slug = _resolve_unique_slug(db, slug_base)

        allowed_tags = ["h2", "h3", "h4", "p", "ul", "ol", "li", "b", "strong", "em", "i", "a", "br", "blockquote"]
        allowed_attrs = {"a": ["href", "title", "rel", "target"]}
        sanitized_content = bleach.clean(
            data.get("content", ""), 
            tags=allowed_tags, 
            attributes=allowed_attrs, 
            protocols=["http", "https", "mailto"],
            strip=True,
            strip_comments=True
        )

        meta_desc = str(data.get("meta_desc", ""))[:160]

        post = BlogPost(
            id=str(uuid.uuid4()),
            title=data.get("title", f"Guide to {keyword}"),
            slug=slug,
            keyword=keyword,
            meta_desc=meta_desc,
            content=sanitized_content,
            word_count=len(sanitized_content.split()),
            published=True,
            created_at=datetime.utcnow()
        )
        db.add(post)
        db.commit()
        logger.info("Created SEO post: %s", post.title)
        return post

    except Exception as e:
        logger.error("SEO engine failed, falling back to deterministic post: %s", e)
        try:
            slug_base = _clean_slug(keyword)
            slug = _resolve_unique_slug(db, slug_base)
            post = BlogPost(
                id=str(uuid.uuid4()),
                title=f"The Complete Guide to {keyword}",
                slug=slug,
                keyword=keyword,
                meta_desc=f"Learn how to master {keyword} with automated AI workflows and proven frameworks."[:160],
                content=f"<h2>Mastering {keyword}</h2><p>In modern e-commerce, speed and conversion matter...</p>",
                word_count=250,
                published=True,
                created_at=datetime.utcnow()
            )
            db.add(post)
            db.commit()
            return post
        except Exception:
            return None
    finally:
        if own_db:
            db.close()


# --- 2. Email Drip Bot ---

def run_drip_campaigns(db: Optional[Session] = None) -> int:
    """Follows up with free users to convert them to paid plans."""
    own_db = False
    if db is None:
        db = SessionLocal()
        own_db = True
    sent_count = 0
    try:
        now = datetime.utcnow()
        users = db.query(User).filter(User.plan == "free").all()

        for user in users:
            age_days = (now - user.created_at).days

            steps = {
                2: (
                    "The secret to high-converting product copy", 
                    "Hi there,<br><br>The biggest mistake marketers make? Talking about features instead of <b>benefits</b>. KopyKat automatically uses proven copywriting frameworks (like AIDA and PAS) to generate copy that actually sells.<br><br><a href='https://kopykat.onrender.com/dashboard'>Log in and try the Ad Copy Generator</a> today."
                ),
                4: (
                    "Save 10+ hours this week with automated copy", 
                    "How much time do you spend staring at a blank screen?<br><br>With KopyKat, you can generate an entire omni-channel campaign (SEO blog, 3 emails, 3 ad angles) in 30 seconds. Use your remaining free generations to see the results yourself."
                ),
                7: (
                    "Your free test drive generations are running low", 
                    "Hey there,<br><br>I hope you have loved using KopyKat. If you want to scale up your multi-channel catalog, it is time to upgrade.<br><br>Our <b>Boutique Plan</b> gives you <b>150 campaigns</b> and multi-platform syndication every month.<br><br><a href='https://kopykat.onrender.com/dashboard'>Upgrade in your dashboard now</a> and automate your catalog operations."
                )
            }

            if age_days in steps:
                already_sent = db.query(DripLog).filter_by(user_id=user.id, step=age_days).first()
                if not already_sent:
                    subject, body = steps[age_days]
                    _send_email(subject, body, user.email)
                    
                    db.add(DripLog(id=str(uuid.uuid4()), user_id=user.id, step=age_days))
                    db.commit()
                    sent_count += 1
                    logger.info("Sent drip day %d to %s", age_days, user.email)
        return sent_count
    except Exception as e:
        logger.error("Drip campaign failed: %s", e)
        return 0
    finally:
        if own_db:
            db.close()


# --- 3. Social Opportunity Scout ---

SUBREDDITS = ["entrepreneur", "smallbusiness", "copywriting", "ecommerce", "marketing"]
SCOUT_KEYWORDS = ["write copy", "product descriptions", "ad copy", "sucks at writing", "need a copywriter", "writing emails"]

async def scan_reddit_opportunities(db: Optional[Session] = None) -> int:
    """Scans Reddit for leads and drafts AI replies."""
    own_db = False
    if db is None:
        db = SessionLocal()
        own_db = True
    found_count = 0
    try:
        headers = {'User-Agent': 'Mozilla/5.0 KopyKatScout/1.0'}
        
        async with httpx.AsyncClient(headers=headers, timeout=5.0) as http_client:
            for sub in SUBREDDITS:
                data = None
                try:
                    r = await http_client.get(f"https://www.reddit.com/r/{sub}/new/.json?limit=15")
                    if r.status_code != 200: continue
                    data = r.json()
                except Exception:
                    continue

                if not data or not isinstance(data, dict):
                    continue

                for post in data.get('data', {}).get('children', []):
                    post_data = post['data']
                    title = post_data.get('title', '')
                    selftext = post_data.get('selftext', '')
                    post_id = post_data.get('id', '')
                    url = "https://reddit.com" + post_data.get('permalink', '')
    
                    text = (title + " " + selftext).lower()
                    
                    if any(kw in text for kw in SCOUT_KEYWORDS):
                        if db.query(OpportunityLog).filter_by(post_id=post_id).first():
                            continue
    
                        draft = f"I used to struggle with drafting product descriptions too until I started using KopyKat (https://kopykat.onrender.com) to automate catalog copy and syndication. Saves a huge amount of time."
                        if (os.environ.get('GEMINI_API_KEY', '').strip() or os.environ.get('OPENAI_API_KEY', '').strip()):
                            try:
                                prompt = f"Write a helpful, non-spammy Reddit reply to this post: '{title}\n{selftext}'. Suggest they try an AI tool called KopyKat (https://kopykat.onrender.com) to automate their copywriting. Keep it under 80 words, sound casual like a real redditor."
                                generated = await _generate_marketing_text(prompt, max_output_tokens=300)
                                if generated:
                                    draft = generated
                            except Exception:
                                pass
    
                        intent_score = 75
                        if any(high_kw in text for high_kw in ["need a copywriter", "hire", "budget", "pay", "sucks at writing", "struggling"]):
                            intent_score += 15
                        if "ecommerce" in sub or "ecommerce" in url or "shopify" in text or "amazon" in text:
                            intent_score += 8
                        intent_score = min(intent_score, 99)
    
                        log = OpportunityLog(
                            id=str(uuid.uuid4()), 
                            platform="reddit", 
                            post_id=post_id, 
                            post_url=url, 
                            post_title=title, 
                            draft_reply=draft, 
                            score=intent_score,
                            alerted=True
                        )
                        db.add(log)
                        db.commit()
                        found_count += 1

                        body = f"Found a lead on r/{sub}!<br><br><b>{title}</b><br><a href='{url}'>{url}</a><br><br><b>Draft Reply to copy/paste:</b><br>{draft}"
                        _send_email(f"New Lead: {title[:30]}...", body, os.environ.get("OWNER_EMAIL", ""))
                        logger.info("Found opportunity on r/%s: %s", sub, title[:30])
        return found_count

    except Exception as e:
        logger.error("Scout failed: %s", e)
        return 0
    finally:
        if own_db:
            db.close()
