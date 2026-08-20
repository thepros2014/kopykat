import logging
import requests
import json
from base64 import b64encode

logger = logging.getLogger(__name__)

# --- PUSH LOGIC ---

def push_to_wordpress(creds: dict, title: str, content: str, meta: dict) -> dict:
    url = creds.get("url", "").rstrip("/")
    username = creds.get("username")
    app_password = creds.get("app_password")
    
    api_url = f"{url}/wp-json/wp/v2/posts"
    token = b64encode(f"{username}:{app_password}".encode()).decode("utf-8")
    headers = {"Authorization": f"Basic {token}", "Content-Type": "application/json"}
    
    data = {"title": title, "content": content, "status": "draft"}
    if meta.get("category_id"):
        data["categories"] = [int(meta["category_id"])]
        
    response = requests.post(api_url, headers=headers, json=data, timeout=10)
    response.raise_for_status()
    return {"success": True, "link": response.json().get("link")}

def push_to_mailchimp(creds: dict, subject: str, content: str, meta: dict) -> dict:
    api_key = creds.get("api_key")
    dc = api_key.split("-")[1] if "-" in api_key else "us1"
    
    api_url = f"https://{dc}.api.mailchimp.com/3.0/campaigns"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    data = {
        "type": "regular",
        "settings": {"subject_line": subject, "title": subject, "reply_to": "hello@example.com", "from_name": "KopyKat"}
    }
    
    list_id = meta.get("list_id") or creds.get("list_id")
    if list_id:
        data["recipients"] = {"list_id": list_id}
        
    response = requests.post(api_url, headers=headers, json=data, timeout=10)
    response.raise_for_status()
    campaign_id = response.json().get("id")
    
    content_url = f"{api_url}/{campaign_id}/content"
    content_response = requests.put(content_url, headers=headers, json={"html": content}, timeout=10)
    content_response.raise_for_status()
    return {"success": True, "campaign_id": campaign_id}

def push_to_hubspot(creds: dict, title: str, content: str, meta: dict) -> dict:
    token = creds.get("access_token")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # Simple push to HubSpot Emails Drafts or standard engagements if no CMS
    api_url = "https://api.hubapi.com/crm/v3/objects/notes"
    data = {
        "properties": {
            "hs_note_body": f"<h1>{title}</h1>{content}"
        }
    }
    
    response = requests.post(api_url, headers=headers, json=data, timeout=10)
    response.raise_for_status()
    return {"success": True}

def push_to_shopify(creds: dict, title: str, content: str, meta: dict) -> dict:
    shop_url = creds.get("shop_url", "").rstrip("/")
    token = creds.get("access_token")
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    
    api_url = f"{shop_url}/admin/api/2024-01/products.json"
    data = {
        "product": {
            "title": title,
            "body_html": content,
            "status": "draft"
        }
    }
    
    response = requests.post(api_url, headers=headers, json=data, timeout=10)
    response.raise_for_status()
    return {"success": True}

def push_to_webflow(creds: dict, title: str, content: str, meta: dict) -> dict:
    token = creds.get("access_token")
    collection_id = meta.get("collection_id") or creds.get("collection_id")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "accept-version": "1.0.0"}
    
    if not collection_id:
        raise ValueError("Webflow requires a collection_id to push CMS items.")
        
    api_url = f"https://api.webflow.com/collections/{collection_id}/items"
    data = {
        "fields": {
            "name": title,
            "slug": title.lower().replace(" ", "-"),
            "post-body": content,
            "_archived": False,
            "_draft": True
        }
    }
    
    response = requests.post(api_url, headers=headers, json=data, timeout=10)
    response.raise_for_status()
    return {"success": True}

# --- METADATA FETCHING ---

def fetch_metadata(platform: str, creds: dict) -> list:
    """Returns a list of dicts: [{'id': '123', 'name': 'Category Name'}]"""
    options = []
    try:
        if platform == "wordpress":
            url = creds.get("url", "").rstrip("/")
            api_url = f"{url}/wp-json/wp/v2/categories"
            token = b64encode(f"{creds.get('username')}:{creds.get('app_password')}".encode()).decode("utf-8")
            headers = {"Authorization": f"Basic {token}"}
            res = requests.get(api_url, headers=headers, timeout=5)
            if res.ok:
                options = [{"id": str(c["id"]), "name": c["name"]} for c in res.json()]
                
        elif platform == "mailchimp":
            api_key = creds.get("api_key", "")
            dc = api_key.split("-")[1] if "-" in api_key else "us1"
            api_url = f"https://{dc}.api.mailchimp.com/3.0/lists"
            headers = {"Authorization": f"Bearer {api_key}"}
            res = requests.get(api_url, headers=headers, timeout=5)
            if res.ok:
                options = [{"id": l["id"], "name": l["name"]} for l in res.json().get("lists", [])]
                
        elif platform == "webflow":
            token = creds.get("access_token")
            site_id = creds.get("site_id")
            if site_id:
                api_url = f"https://api.webflow.com/sites/{site_id}/collections"
                headers = {"Authorization": f"Bearer {token}", "accept-version": "1.0.0"}
                res = requests.get(api_url, headers=headers, timeout=5)
                if res.ok:
                    options = [{"id": c["_id"], "name": c["name"]} for c in res.json()]
    except Exception as e:
        logger.warning(f"Failed to fetch metadata for {platform}: {e}")
        
    return options

# --- ASYNC JOB EXECUTION ---

def background_push(platform: str, creds: dict, title: str, content: str, meta: dict, integration_id: str, job_id: str):
    from .database import SessionLocal, UserIntegration, PushJob
    from datetime import datetime
    
    db = SessionLocal()
    try:
        job = db.query(PushJob).filter(PushJob.id == job_id).first()
        if job:
            job.status = "processing"
            db.commit()
        
        if platform == "wordpress":
            push_to_wordpress(creds, title, content, meta)
        elif platform == "mailchimp":
            push_to_mailchimp(creds, title, content, meta)
        elif platform == "hubspot":
            push_to_hubspot(creds, title, content, meta)
        elif platform == "shopify":
            push_to_shopify(creds, title, content, meta)
        elif platform == "webflow":
            push_to_webflow(creds, title, content, meta)
            
        integration = db.query(UserIntegration).filter(UserIntegration.id == integration_id).first()
        if integration:
            integration.last_synced_at = datetime.utcnow()
            integration.status = "connected"
            
        if job:
            job.status = "success"
            job.details = f"Successfully pushed to {platform}."
            
        db.commit()
    except Exception as e:
        logger.error(f"Background Push failed for {platform}: {e}")
        integration = db.query(UserIntegration).filter(UserIntegration.id == integration_id).first()
        if integration:
            integration.status = "error"
            
        job = db.query(PushJob).filter(PushJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.details = str(e)
            
        db.commit()
    finally:
        db.close()
