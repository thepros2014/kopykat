with open("server/integrations.py", "r", encoding="utf-8") as f:
    code = f.read()

header = """import logging
import requests
import json
from base64 import b64encode

logger = logging.getLogger(__name__)

job_status_store = {}
"""
code = code.replace("logger = logging.getLogger(__name__)", header)

old_bg = """def background_push(platform: str, creds: dict, title: str, content: str, integration_id: str):
    from .database import SessionLocal, UserIntegration
    from datetime import datetime
    
    db = SessionLocal()
    try:
        if platform == "wordpress":
            push_to_wordpress(creds, title, content)
        elif platform == "mailchimp":
            push_to_mailchimp(creds, title, content)
            
        integration = db.query(UserIntegration).filter(UserIntegration.id == integration_id).first()
        if integration:
            integration.last_synced_at = datetime.utcnow()
            integration.status = "connected"
            db.commit()
    except Exception as e:
        logger.error(f"Background Push failed for {platform}: {e}")
        integration = db.query(UserIntegration).filter(UserIntegration.id == integration_id).first()
        if integration:
            integration.status = "error"
            db.commit()
    finally:
        db.close()"""

new_bg = """def background_push(platform: str, creds: dict, title: str, content: str, integration_id: str, job_id: str):
    from .database import SessionLocal, UserIntegration
    from datetime import datetime
    
    db = SessionLocal()
    try:
        job_status_store[job_id] = {"status": "processing", "details": None}
        
        if platform == "wordpress":
            push_to_wordpress(creds, title, content)
        elif platform == "mailchimp":
            push_to_mailchimp(creds, title, content)
            
        integration = db.query(UserIntegration).filter(UserIntegration.id == integration_id).first()
        if integration:
            integration.last_synced_at = datetime.utcnow()
            integration.status = "connected"
            db.commit()
            
        job_status_store[job_id]["status"] = "success"
        job_status_store[job_id]["details"] = f"Successfully pushed to {platform}."
    except Exception as e:
        logger.error(f"Background Push failed for {platform}: {e}")
        integration = db.query(UserIntegration).filter(UserIntegration.id == integration_id).first()
        if integration:
            integration.status = "error"
            db.commit()
            
        job_status_store[job_id]["status"] = "failed"
        job_status_store[job_id]["details"] = str(e)
    finally:
        db.close()"""

code = code.replace(old_bg, new_bg)

with open("server/integrations.py", "w", encoding="utf-8") as f:
    f.write(code)
