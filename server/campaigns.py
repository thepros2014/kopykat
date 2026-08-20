import json
import os
import logging
import random
import google.generativeai as genai

logger = logging.getLogger(__name__)

def scrape_pain_points(keyword: str) -> str:
    """
    Simulates a social listening tool (like scraping Reddit/Twitter).
    In a real production environment, this would call Serper/Reddit API.
    """
    logger.info(f"Scraping social pain points for: {keyword}")
    
    # Mocked social signals for the MVP
    pain_points = [
        "Users are frustrated by how complicated existing tools are. They want '1-click' solutions.",
        f"People complain that {keyword} is too expensive for small businesses.",
        "A common thread on Reddit mentions terrible customer support in this industry.",
        "Users hate paying for features they don't use. They want modular pricing.",
        "There's a massive gap in automation; users are manually transferring data between platforms."
    ]
    
    selected = random.sample(pain_points, 3)
    return " | ".join(selected)

def generate_omni_campaign(keyword: str, product_desc: str) -> dict:
    """
    Generates a full cohesive campaign (Blog, Emails, Social) based on market pain points.
    """
    pain_points = scrape_pain_points(keyword)
    
    genai.configure(api_key=os.environ.get('GEMINI_API_KEY', ''))
    # Use flash for speed
    model = genai.GenerativeModel(os.environ.get('GEMINI_MODEL', 'gemini-1.5-flash'))
    
    prompt = f"""You are an elite direct-response marketer and copywriter.
    
We are selling the following product/service: {product_desc}
Target Keyword/Market: {keyword}

I just scraped social media (Reddit/Twitter) for what this market is currently complaining about. 
Here are their active pain points: {pain_points}

Your job is to generate a cohesive Omni-Channel Marketing Campaign that directly addresses these pain points.
Format your output as a STRICT JSON object with no markdown wrappers (do not use ```json).
The JSON must have the following exact structure:

{{
  "blog_post": {{
    "title": "A catchy, SEO-optimized title",
    "content": "The full blog post in HTML format (using <h2>, <h3>, <p>, <ul>). It should address the pain points."
  }},
  "email_drip": [
    {{
      "subject": "Subject for Email 1 (Problem Awareness)",
      "body": "HTML body for email 1 using PAS framework."
    }},
    {{
      "subject": "Subject for Email 2 (Agitation & Solution)",
      "body": "HTML body for email 2."
    }},
    {{
      "subject": "Subject for Email 3 (Urgency/Offer)",
      "body": "HTML body for email 3."
    }}
  ],
  "social_posts": [
    "Engaging Twitter/LinkedIn style post 1",
    "Engaging Twitter/LinkedIn style post 2",
    "Engaging Twitter/LinkedIn style post 3"
  ]
}}
"""
    
    response = model.generate_content(prompt)
    text = response.text.strip()
    
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
        
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Omni-Campaign JSON: {text}")
        raise ValueError("AI returned invalid campaign formatting. Please try again.")

