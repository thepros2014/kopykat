"""
marketing.py — The fully automated marketing engine.
Contains the SEO Blog Engine, Email Drip Bot, and Opportunity Scout.
"""

import os
import uuid
import json
import logging
import random
import requests
from datetime import datetime, timedelta

import google.generativeai as genai
from sqlalchemy.orm import Session

from .database import SessionLocal, BlogPost, User, DripLog, OpportunityLog
from .scheduler import _send_email

logger = logging.getLogger(__name__)

# ── 1. SEO Blog Engine ────────────────────────────────────────────────────────

KEYWORDS = [
    "AI copywriting for ecommerce", 
    "How to write product descriptions with AI",
    "Best AI tools for marketing agencies", 
    "Automate social media copy",
    "AI email sequence generator", 
    "Write better Facebook ads with AI",
    "Copywriting tips for startups",
    "How to increase conversion rates with AI",
    "AI landing page generator"
]

async def generate_seo_post():
    """Generates and publishes an SEO-optimized blog post."""
    db = SessionLocal()
    try:
        keyword = random.choice(KEYWORDS)
        logger.info(f"Starting SEO blog generation for: {keyword}")

        genai.configure(api_key=os.environ.get('GEMINI_API_KEY', ''))
        model = genai.GenerativeModel(os.environ.get('GEMINI_MODEL', 'gemini-flash-latest'))

        prompt = f"""Write an SEO-optimized blog post about '{keyword}'.
        Output strictly as a JSON object with these exact keys:
        - "title": a catchy SEO title
        - "slug": url-friendly-slug-of-title
        - "meta_desc": 150 char meta description
        - "content": the full blog post in HTML format (using <h2>, <h3>, <p>, <ul>). Include a subtle pitch for SnapCopy AI at the end. Do not include markdown wrappers around the HTML.
        
        Return ONLY valid JSON.
        """
        response = await model.generate_content_async(prompt)
        text = response.text.strip()
        if text.startswith('```json'): text = text[7:]
        if text.endswith('```'): text = text[:-3]
        text = text.strip()

        data = json.loads(text)

        # Check if slug exists
        if db.query(BlogPost).filter(BlogPost.slug == data["slug"]).first():
            data["slug"] = data["slug"] + "-" + str(random.randint(100, 999))

        post = BlogPost(
            id=str(uuid.uuid4()),
            title=data["title"],
            slug=data["slug"],
            keyword=keyword,
            meta_desc=data["meta_desc"],
            content=data["content"],
            word_count=len(data["content"].split())
        )
        db.add(post)
        db.commit()
        logger.info(f"Created SEO post: {post.title}")

    except Exception as e:
        logger.error(f"SEO engine failed: {e}")
    finally:
        db.close()


# ── 2. Email Drip Bot ─────────────────────────────────────────────────────────

def run_drip_campaigns():
    """Follows up with free users to convert them to paid."""
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        users = db.query(User).filter(User.plan == "free").all()

        for user in users:
            age_days = (now - user.created_at).days

            # Drip schedule
            steps = {
                1: ("Welcome to SnapCopy AI 🚀", "Hi!<br><br>Thanks for joining. You have 5,000 free tokens to generate high-converting copy.<br><br>Log in and make your first API call today!"),
                3: ("How's your copy looking?", "Just checking in. Have you tried the Product Description or Social Post generator yet? It'll save you hours this week."),
                7: ("Your free tokens are expiring soon...", "Time to upgrade to the Basic Plan for just $9/mo to keep the copy flowing and unlock more keys.<br><br>Upgrade in your dashboard.")
            }

            if age_days in steps:
                already_sent = db.query(DripLog).filter_by(user_id=user.id, step=age_days).first()
                if not already_sent:
                    subject, body = steps[age_days]
                    _send_email(subject, body, user.email)
                    
                    db.add(DripLog(id=str(uuid.uuid4()), user_id=user.id, step=age_days))
                    db.commit()
                    logger.info(f"Sent drip day {age_days} to {user.email}")
    except Exception as e:
        logger.error(f"Drip campaign failed: {e}")
    finally:
        db.close()


# ── 3. Opportunity Scout ──────────────────────────────────────────────────────

SUBREDDITS = ["entrepreneur", "smallbusiness", "copywriting", "ecommerce", "marketing"]
SCOUT_KEYWORDS = ["write copy", "product descriptions", "ad copy", "sucks at writing", "need a copywriter", "writing emails"]

async def scan_reddit_opportunities():
    """Scans Reddit for leads and drafts AI replies."""
    db = SessionLocal()
    try:
        genai.configure(api_key=os.environ.get('GEMINI_API_KEY', ''))
        model = genai.GenerativeModel(os.environ.get('GEMINI_MODEL', 'gemini-flash-latest'))

        headers = {'User-Agent': 'Mozilla/5.0 SnapCopyScout/1.0'}
        
        for sub in SUBREDDITS:
            r = requests.get(f"https://www.reddit.com/r/{sub}/new/.json?limit=15", headers=headers)
            if r.status_code != 200: continue

            data = r.json()
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

                    # Draft reply
                    prompt = f"Write a helpful, non-spammy Reddit reply to this post: '{title}\n{selftext}'. Suggest they try an AI tool called SnapCopy AI (https://snapcopy-ai.onrender.com) to automate their copywriting. Keep it under 80 words, sound casual like a real redditor."
                    response = await model.generate_content_async(prompt)
                    draft = response.text.strip()

                    log = OpportunityLog(
                        id=str(uuid.uuid4()), 
                        platform="reddit", 
                        post_id=post_id, 
                        post_url=url, 
                        post_title=title, 
                        draft_reply=draft, 
                        alerted=True
                    )
                    db.add(log)
                    db.commit()

                    # Email owner
                    body = f"Found a lead on r/{sub}!<br><br><b>{title}</b><br><a href='{url}'>{url}</a><br><br><b>Draft Reply to copy/paste:</b><br>{draft}"
                    _send_email(f"New Lead: {title[:30]}...", body, os.environ.get("OWNER_EMAIL", ""))
                    logger.info(f"Found opportunity on r/{sub}: {title[:30]}")

    except Exception as e:
        logger.error(f"Scout failed: {e}")
    finally:
        db.close()
