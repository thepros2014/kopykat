import ipaddress
import logging
import requests
import socket
from base64 import b64encode
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _validate_external_url(url: str, *, allowed_schemes=("https",), allow_http=False) -> str:
    """Validate customer-supplied outbound URLs and block SSRF targets."""
    if not url or not isinstance(url, str):
        raise ValueError("A valid integration URL is required.")
    parsed = urlparse(url.strip())
    schemes = set(allowed_schemes)
    if allow_http:
        schemes.add("http")
    if parsed.scheme.lower() not in schemes or not parsed.hostname:
        raise ValueError("Integration URL must use a valid HTTPS URL.")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        raise ValueError("Local integration URLs are not allowed.")
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
        addresses = {info[4][0] for info in infos}
    except socket.gaierror as exc:
        raise ValueError("Integration host could not be resolved.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError("Integration host resolves to a restricted network address.")
    return url.strip().rstrip("/")


# --- PUSH LOGIC ---

def push_to_wordpress(creds: dict, title: str, content: str, meta: dict) -> dict:
    url = _validate_external_url(creds.get("url", ""))
    username = creds.get("username")
    app_password = creds.get("app_password")
    if not username or not app_password:
        raise ValueError("WordPress credentials are incomplete.")
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
    if not api_key:
        raise ValueError("Mailchimp API key is required.")
    dc = api_key.split("-")[1] if "-" in api_key else "us1"
    api_url = f"https://{dc}.api.mailchimp.com/3.0/campaigns"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = {"type": "regular", "settings": {"subject_line": subject, "title": subject, "reply_to": "hello@example.com", "from_name": "KopyKat"}}
    list_id = meta.get("list_id") or creds.get("list_id")
    if list_id:
        data["recipients"] = {"list_id": list_id}
    response = requests.post(api_url, headers=headers, json=data, timeout=10)
    response.raise_for_status()
    campaign_id = response.json().get("id")
    content_response = requests.put(f"{api_url}/{campaign_id}/content", headers=headers, json={"html": content}, timeout=10)
    content_response.raise_for_status()
    return {"success": True, "campaign_id": campaign_id}


def push_to_hubspot(creds: dict, title: str, content: str, meta: dict) -> dict:
    token = creds.get("access_token")
    if not token:
        raise ValueError("HubSpot access token is required.")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.post("https://api.hubapi.com/crm/v3/objects/notes", headers=headers, json={"properties": {"hs_note_body": f"<h1>{title}</h1>{content}"}}, timeout=10)
    response.raise_for_status()
    return {"success": True}


def push_to_shopify(creds: dict, title: str, content: str, meta: dict) -> dict:
    shop_url = _validate_external_url(creds.get("shop_url", ""))
    token = creds.get("access_token")
    if not token:
        raise ValueError("Shopify access token is required.")
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    response = requests.post(f"{shop_url}/admin/api/2024-01/products.json", headers=headers, json={"product": {"title": title, "body_html": content, "status": "draft"}}, timeout=10)
    response.raise_for_status()
    return {"success": True}


def push_to_webflow(creds: dict, title: str, content: str, meta: dict) -> dict:
    token = creds.get("access_token")
    collection_id = meta.get("collection_id") or creds.get("collection_id")
    if not token or not collection_id:
        raise ValueError("Webflow access token and collection_id are required.")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "accept-version": "1.0.0"}
    response = requests.post(f"https://api.webflow.com/collections/{collection_id}/items", headers=headers, json={"fields": {"name": title, "slug": title.lower().replace(" ", "-"), "post-body": content, "_archived": False, "_draft": True}}, timeout=10)
    response.raise_for_status()
    return {"success": True}


def _unsupported_marketplace(platform: str):
    raise NotImplementedError(f"{platform.title()} publishing is not yet enabled. Credentials were not used and no fake success is reported.")


def push_to_amazon(creds: dict, title: str, content: str, meta: dict) -> dict:
    return _unsupported_marketplace("Amazon")


def push_to_ebay(creds: dict, title: str, content: str, meta: dict) -> dict:
    return _unsupported_marketplace("eBay")


def push_to_walmart(creds: dict, title: str, content: str, meta: dict) -> dict:
    return _unsupported_marketplace("Walmart")


def push_to_temu(creds: dict, title: str, content: str, meta: dict) -> dict:
    return _unsupported_marketplace("Temu")


def fetch_metadata(platform: str, creds: dict) -> list:
    options = []
    try:
        if platform == "wordpress":
            url = _validate_external_url(creds.get("url", ""))
            api_url = f"{url}/wp-json/wp/v2/categories"
            token = b64encode(f"{creds.get('username')}:{creds.get('app_password')}".encode()).decode("utf-8")
            res = requests.get(api_url, headers={"Authorization": f"Basic {token}"}, timeout=5)
            if res.ok:
                options = [{"id": str(c["id"]), "name": c["name"]} for c in res.json()]
        elif platform == "mailchimp":
            api_key = creds.get("api_key", "")
            dc = api_key.split("-")[1] if "-" in api_key else "us1"
            res = requests.get(f"https://{dc}.api.mailchimp.com/3.0/lists", headers={"Authorization": f"Bearer {api_key}"}, timeout=5)
            if res.ok:
                options = [{"id": l["id"], "name": l["name"]} for l in res.json().get("lists", [])]
        elif platform == "webflow":
            token = creds.get("access_token")
            site_id = creds.get("site_id")
            if site_id and token:
                res = requests.get(f"https://api.webflow.com/sites/{site_id}/collections", headers={"Authorization": f"Bearer {token}", "accept-version": "1.0.0"}, timeout=5)
                if res.ok:
                    options = [{"id": c["_id"], "name": c["name"]} for c in res.json()]
    except Exception as e:
        logger.warning("Failed to fetch metadata for %s: %s", platform, e)
    return options


def background_push(platform: str, creds: dict, title: str, content: str, meta: dict, integration_id: str, job_id: str):
    from .database import SessionLocal, UserIntegration, PushJob
    from datetime import datetime
    db = SessionLocal()
    try:
        job = db.query(PushJob).filter(PushJob.id == job_id).first()
        if job:
            job.status = "processing"
            db.commit()
        dispatch = {
            "wordpress": push_to_wordpress,
            "mailchimp": push_to_mailchimp,
            "hubspot": push_to_hubspot,
            "shopify": push_to_shopify,
            "webflow": push_to_webflow,
            "amazon": push_to_amazon,
            "ebay": push_to_ebay,
            "walmart": push_to_walmart,
            "temu": push_to_temu,
        }
        if platform not in dispatch:
            raise ValueError(f"Unsupported integration platform: {platform}")
        dispatch[platform](creds, title, content, meta)
        integration = db.query(UserIntegration).filter(UserIntegration.id == integration_id).first()
        if integration:
            integration.last_synced_at = datetime.utcnow()
            integration.status = "connected"
        if job:
            job.status = "success"
            job.details = f"Successfully pushed to {platform}."
        db.commit()
    except Exception as e:
        logger.error("Background Push failed for %s: %s", platform, e)
        integration = db.query(UserIntegration).filter(UserIntegration.id == integration_id).first()
        if integration:
            integration.status = "error"
        job = db.query(PushJob).filter(PushJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.details = str(e)[:1000]
        db.commit()
    finally:
        db.close()
