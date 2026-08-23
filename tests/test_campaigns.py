import pytest
import base64
from server.database import User, Campaign

def test_campaign_generate_atomic_credit_deduction(client, db_session, test_user, auth_headers, monkeypatch):
    # Mock omni campaign generator
    mock_assets = {
        "blog_post": {"title": "Best Leather Wallets 2026", "content": "<p>Review</p>"},
        "email_drip": [{"subject": "Never lose your cards", "body": "<p>Story</p>"}],
        "social_posts": ["Check out our new wallet!"]
    }
    monkeypatch.setattr("server.campaigns.generate_omni_campaign", lambda kw, desc: mock_assets)
    
    initial_generations = test_user.generations
    
    res = client.post(
        "/api/campaign/generate",
        json={"keyword": "Leather Wallet", "product_desc": "Handcrafted full grain leather wallet"},
        headers=auth_headers
    )
    
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Campaign: Leather Wallet"
    assert data["assets"]["blog_post"]["title"] == "Best Leather Wallets 2026"
    
    # Invariant check: Generations count decremented by 1 atomically
    db_session.expire_all()
    user = db_session.query(User).filter(User.id == test_user.id).first()
    assert user.generations == initial_generations - 1

def test_campaign_generate_insufficient_credits(client, db_session, test_user, auth_headers):
    # Set user generations to 0
    test_user.generations = 0
    db_session.commit()
    
    res = client.post(
        "/api/campaign/generate",
        json={"keyword": "Leather Wallet", "product_desc": "Handcrafted full grain leather wallet"},
        headers=auth_headers
    )
    
    assert res.status_code == 402
    assert "Insufficient campaigns" in res.json()["detail"]

def test_campaign_vision_generate(client, db_session, test_user, auth_headers, monkeypatch):
    test_user.generations = 5
    db_session.commit()
    
    mock_vision_assets = {
        "detected_product_name": "Premium Vintage Leather Bag",
        "detected_description": "Handcrafted genuine leather messenger bag.",
        "blog_post": {"title": "Why You Need a Leather Bag", "content": "<p>Content</p>"},
        "email_drip": [{"subject": "Upgrade your style", "body": "<p>Email</p>"}],
        "social_posts": ["New arrival!"]
    }
    monkeypatch.setattr("server.campaigns.generate_omni_campaign_from_image", lambda **kwargs: mock_vision_assets)
    
    fake_img_b64 = base64.b64encode(b"fake-image-bytes-for-unit-test").decode('utf-8')
    
    res = client.post(
        "/api/campaign/generate-vision",
        json={
            "image_base64": fake_img_b64,
            "mime_type": "image/jpeg",
            "keyword": "Leather Bag",
            "extra_context": "Brown color"
        },
        headers=auth_headers
    )
    
    assert res.status_code == 200
    data = res.json()
    assert "Vision Campaign: Premium Vintage Leather Bag" in data["name"]
    assert data["assets"]["detected_product_name"] == "Premium Vintage Leather Bag"
    
    # Check DB record
    camp = db_session.query(Campaign).filter(Campaign.id == data["id"]).first()
    assert camp is not None
