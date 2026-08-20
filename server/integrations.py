import logging
import requests
import json
from base64 import b64encode

logger = logging.getLogger(__name__)

def push_to_wordpress(credentials: dict, title: str, content: str) -> dict:
    url = credentials.get("url", "").rstrip("/")
    username = credentials.get("username")
    app_password = credentials.get("app_password")

    if not url or not username or not app_password:
        raise ValueError("Missing WordPress credentials (url, username, app_password)")

    api_url = f"{url}/wp-json/wp/v2/posts"
    token = b64encode(f"{username}:{app_password}".encode()).decode("utf-8")
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json"
    }
    
    data = {
        "title": title,
        "content": content,
        "status": "draft"
    }

    try:
        response = requests.post(api_url, headers=headers, json=data, timeout=10)
        response.raise_for_status()
        res_data = response.json()
        return {"success": True, "link": res_data.get("link")}
    except Exception as e:
        logger.error(f"WordPress Push Error: {e}")
        raise ValueError(f"Failed to push to WordPress: {str(e)}")


def push_to_mailchimp(credentials: dict, subject: str, content: str) -> dict:
    api_key = credentials.get("api_key")
    list_id = credentials.get("list_id")  # optional if we just want a generic draft, but usually needed
    
    if not api_key:
        raise ValueError("Missing Mailchimp API key")
        
    try:
        dc = api_key.split("-")[1]
    except IndexError:
        raise ValueError("Invalid Mailchimp API key format")

    api_url = f"https://{dc}.api.mailchimp.com/3.0/campaigns"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Simplified campaign creation (regular)
    data = {
        "type": "regular",
        "settings": {
            "subject_line": subject,
            "title": subject,
            "reply_to": "hello@example.com",
            "from_name": "SnapCopy AI User"
        }
    }
    
    if list_id:
        data["recipients"] = {"list_id": list_id}

    try:
        # Create campaign
        response = requests.post(api_url, headers=headers, json=data, timeout=10)
        response.raise_for_status()
        campaign_id = response.json().get("id")

        # Set content
        content_url = f"{api_url}/{campaign_id}/content"
        content_data = {
            "html": content
        }
        content_response = requests.put(content_url, headers=headers, json=content_data, timeout=10)
        content_response.raise_for_status()

        return {"success": True, "campaign_id": campaign_id}
    except Exception as e:
        logger.error(f"Mailchimp Push Error: {e}")
        raise ValueError(f"Failed to push to Mailchimp: {str(e)}")
