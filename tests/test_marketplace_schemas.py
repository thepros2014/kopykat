"""
tests/test_marketplace_schemas.py - Unit and integration tests for Milestone 1:
Multi-Modal Campaign & Multi-Platform Listing Schemas (Amazon, Shopify, Etsy, TikTok Shop, eBay).

Strict Zero-Emoji Policy Enforced.
"""

import os
import base64
import json
import re
import uuid
from unittest.mock import patch, AsyncMock
import pytest
from pydantic import ValidationError

from server.models import (
    MarketplaceOptimizeRequest,
    MarketplaceOptimizeResponse,
    CampaignVisionGenerateRequest,
)
from server.ai_engine import optimize_marketplace_listing
from server.campaigns import (
    generate_omni_campaign_from_image,
    _generate_fallback_vision_campaign,
    _extract_clean_json,
)
from server.database import User, BrandPersona, Campaign, UserEntitlement
from server.auth import create_access_token

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


# ============================================================================
# 1. PLATFORM ENUM / REGEX VALIDATION TESTS
# ============================================================================

@pytest.mark.parametrize("valid_platform", [
    "amazon", "shopify", "etsy", "tiktok", "tiktok_shop", "ebay"
])
def test_marketplace_request_valid_platforms(valid_platform):
    """Verifies that all 6 platform enum values are accepted by MarketplaceOptimizeRequest."""
    req = MarketplaceOptimizeRequest(
        product_name="Pro Noise Cancelling Earbuds",
        platform=valid_platform,
        raw_details="Wireless earbuds with 30h playtime and ANC.",
        keywords="wireless earbuds, anc headphones"
    )
    assert req.platform == valid_platform


@pytest.mark.parametrize("invalid_platform", [
    "walmart", "temu", "aliexpress", "target", "facebook", "instagram", "google", "unknown"
])
def test_marketplace_request_invalid_platforms_raise_error(invalid_platform):
    """Verifies that non-supported platforms are rejected with ValidationError."""
    with pytest.raises(ValidationError):
        MarketplaceOptimizeRequest(
            product_name="Pro Noise Cancelling Earbuds",
            platform=invalid_platform,
            raw_details="Wireless earbuds with 30h playtime and ANC."
        )


def test_marketplace_optimizer_endpoint_rejects_invalid_platform_422(client, auth_headers, test_user, db_session):
    """HTTP endpoint returns 422 Unprocessable Entity for invalid platforms."""
    res = client.post(
        "/api/optimizer/marketplace-listing",
        headers=auth_headers,
        json={
            "product_name": "Invalid Platform Item",
            "platform": "walmart",
            "raw_details": "Some description here."
        }
    )
    assert res.status_code == 422


# ============================================================================
# 2. DETERMINISTIC OFFLINE FALLBACKS & SCHEMA CONSTRAINTS
# ============================================================================

@pytest.mark.asyncio
async def test_amazon_listing_schema_and_constraints():
    """Amazon listing fallback: title < 200 chars, 5 bullets with capitalized hooks, search terms < 249 bytes UTF-8, score >= 90."""
    with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
        res = await optimize_marketplace_listing(
            product_name="Ergonomic Lumbar Support Office Chair",
            platform="amazon",
            raw_details="Breathable mesh, 3D armrests, heavy duty base."
        )

    assert res["platform"] == "amazon"
    assert len(res["optimized_title"]) <= 200
    assert len(res["bullet_points"]) == 5
    for bp in res["bullet_points"]:
        assert len(bp) > 10
        assert ":" in bp  # Capitalized hook followed by colon
    
    search_terms = res["backend_search_terms"]
    assert len(search_terms.encode("utf-8")) < 249
    assert "," not in search_terms  # Space-separated, no commas
    assert res["compliance_score"] >= 90
    assert "<p>" in res["structured_description"]
    assert len(EMOJI_PATTERN.findall(str(res))) == 0


@pytest.mark.asyncio
async def test_shopify_listing_schema_and_constraints():
    """Shopify listing fallback: title < 70 chars, meta < 155 chars, 4 bullets, DTC HTML, score >= 90."""
    with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
        res = await optimize_marketplace_listing(
            product_name="Ultra Hydrating Vitamin C Face Serum with Hyaluronic Acid",
            platform="shopify",
            raw_details="Brightening serum with 20% active Vitamin C and botanicals."
        )

    assert res["platform"] == "shopify"
    assert len(res["optimized_title"]) <= 70
    assert len(res["meta_description"]) <= 155
    assert len(res["bullet_points"]) == 4
    assert "<h2>" in res["structured_description"]
    assert res["compliance_score"] >= 90
    assert len(EMOJI_PATTERN.findall(str(res))) == 0


@pytest.mark.asyncio
async def test_etsy_listing_schema_and_constraints():
    """Etsy listing fallback: title < 140 chars, 13 long-tail tags (< 20 chars each), 3-4 bullets, score >= 90."""
    with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
        res = await optimize_marketplace_listing(
            product_name="Handmade Ceramic Stoneware Coffee Mug with Gold Glaze Rim",
            platform="etsy",
            raw_details="Hand thrown 12oz mug crafted from natural clay."
        )

    assert res["platform"] == "etsy"
    assert len(res["optimized_title"]) <= 140
    tags = res["tags"]
    assert len(tags) == 13
    for tag in tags:
        assert len(tag) < 20
        assert len(tag) > 0
    assert 3 <= len(res["bullet_points"]) <= 4
    assert res["compliance_score"] >= 90
    assert len(EMOJI_PATTERN.findall(str(res))) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("platform_name", ["tiktok", "tiktok_shop"])
async def test_tiktok_shop_listing_schema_and_constraints(platform_name):
    """TikTok Shop fallback: title < 100 chars, 3-5 bullets, 3 video hooks, 5-8 hashtags, score >= 90."""
    with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
        res = await optimize_marketplace_listing(
            product_name="Magnetic Wireless Fast Charging Power Bank",
            platform=platform_name,
            raw_details="10000mAh slim battery pack with MagSafe compatibility."
        )

    assert res["platform"] == platform_name
    assert len(res["optimized_title"]) <= 100
    assert 3 <= len(res["bullet_points"]) <= 5
    assert len(res["short_hooks"]) == 3
    for hook in res["short_hooks"]:
        assert len(hook) > 10
    
    assert 5 <= len(res["hashtags"]) <= 8
    for tag in res["hashtags"]:
        assert tag.startswith("#")
    
    assert res["compliance_score"] >= 90
    assert "<p>" in res["structured_description"]
    assert len(EMOJI_PATTERN.findall(str(res))) == 0


@pytest.mark.asyncio
async def test_ebay_listing_schema_and_constraints():
    """eBay listing fallback: title < 80 chars, subtitle < 55 chars, item_specifics dict, 3-4 bullets, score >= 90."""
    with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
        res = await optimize_marketplace_listing(
            product_name="Vintage Automatic Mechanical Chronograph Wrist Watch",
            platform="ebay",
            raw_details="Stainless steel case with sapphire crystal and genuine leather strap."
        )

    assert res["platform"] == "ebay"
    assert len(res["optimized_title"]) <= 80
    assert len(res["sub_title"]) <= 55
    assert isinstance(res["item_specifics"], dict)
    assert "Brand" in res["item_specifics"]
    assert "Condition" in res["item_specifics"]
    assert "MPN" in res["item_specifics"]
    assert 3 <= len(res["bullet_points"]) <= 4
    assert "<div class='ebay-template'>" in res["structured_description"]
    assert res["compliance_score"] >= 90
    assert len(EMOJI_PATTERN.findall(str(res))) == 0


@pytest.mark.asyncio
async def test_extreme_long_title_clamping():
    """Verifies that excessively long product names are strictly clamped to each platform's character cap."""
    long_name = "Super Ultra Deluxe Maximum Edition Premium Handcrafted Custom Multi-Function " * 5
    with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
        res_amazon = await optimize_marketplace_listing(long_name, "amazon", "Details")
        assert len(res_amazon["optimized_title"]) <= 200

        res_shopify = await optimize_marketplace_listing(long_name, "shopify", "Details")
        assert len(res_shopify["optimized_title"]) <= 70

        res_etsy = await optimize_marketplace_listing(long_name, "etsy", "Details")
        assert len(res_etsy["optimized_title"]) <= 140

        res_tiktok = await optimize_marketplace_listing(long_name, "tiktok_shop", "Details")
        assert len(res_tiktok["optimized_title"]) <= 100

        res_ebay = await optimize_marketplace_listing(long_name, "ebay", "Details")
        assert len(res_ebay["optimized_title"]) <= 80
        assert len(res_ebay["sub_title"]) <= 55


# ============================================================================
# 3. ENDPOINT INTEGRATION & RESPONSE SERIALIZATION
# ============================================================================

def test_endpoint_returns_all_new_fields_for_tiktok_and_ebay(client, auth_headers, test_user, db_session):
    """Tests /api/optimizer/marketplace-listing response serialization with new schema fields."""

    # 1. TikTok Shop
    res_tt = client.post(
        "/api/optimizer/marketplace-listing",
        headers=auth_headers,
        json={
            "product_name": "RGB Sunset Projection Lamp",
            "platform": "tiktok_shop",
            "raw_details": "16-color rotating halo light with remote control."
        }
    )
    assert res_tt.status_code == 200
    data_tt = res_tt.json()
    assert data_tt["platform"] == "tiktok_shop"
    assert len(data_tt["short_hooks"]) == 3
    assert len(data_tt["hashtags"]) >= 5
    assert data_tt["compliance_score"] >= 90

    # 2. eBay
    res_ebay = client.post(
        "/api/optimizer/marketplace-listing",
        headers=auth_headers,
        json={
            "product_name": "Original Wireless Bluetooth Gaming Headset",
            "platform": "ebay",
            "raw_details": "Low latency 2.4GHz with RGB lighting and mic."
        }
    )
    assert res_ebay.status_code == 200
    data_ebay = res_ebay.json()
    assert data_ebay["platform"] == "ebay"
    assert data_ebay["sub_title"] is not None
    assert isinstance(data_ebay["item_specifics"], dict)
    assert len(data_ebay["item_specifics"]) >= 3
    assert data_ebay["compliance_score"] >= 90


# ============================================================================
# 4. VISION PIPELINE DUAL-BUCKET RESERVATION & REFUND TESTS
# ============================================================================

def test_vision_pipeline_dual_bucket_reservation_prioritizes_monthly(client, auth_headers, test_user, db_session):
    """Vision generation prioritizes monthly_generations over purchased_generations."""
    test_user.monthly_generations = 5
    test_user.purchased_generations = 10
    test_user.generations = 15
    db_session.commit()

    sample_b64 = base64.b64encode(b"sample_product_image_payload").decode("utf-8")
    mock_campaign = _generate_fallback_vision_campaign("Leather Wallet", "Handmade")

    with patch("server.campaigns.generate_omni_campaign_from_image", return_value=mock_campaign):
        res = client.post(
            "/api/campaign/generate-vision",
            headers=auth_headers,
            json={"image_base64": sample_b64, "mime_type": "image/jpeg", "keyword": "Leather Wallet"}
        )
        assert res.status_code == 200
        data = res.json()
        assert "id" in data
        assert "Vision Campaign" in data["name"]

    # Verify credit deducted from monthly bucket
    db_session.expire_all()
    u = db_session.query(User).filter(User.id == test_user.id).first()
    assert u.monthly_generations == 4
    assert u.purchased_generations == 10
    assert u.generations == 14


def test_vision_pipeline_dual_bucket_refund_on_ai_failure(client, auth_headers, test_user, db_session):
    """Vision generation refunds reserved balance exactly when upstream AI generation throws an error."""
    test_user.monthly_generations = 0
    test_user.purchased_generations = 5
    test_user.generations = 5
    db_session.commit()

    sample_b64 = base64.b64encode(b"valid_image_bytes_xyz").decode("utf-8")

    with patch("server.campaigns.generate_omni_campaign_from_image", side_effect=ValueError("AI model unavailable")):
        res = client.post(
            "/api/campaign/generate-vision",
            headers=auth_headers,
            json={"image_base64": sample_b64}
        )
        assert res.status_code == 400
        assert "AI model unavailable" in res.json()["detail"]

    # Invariant: Balance was preserved and restored to purchased bucket
    db_session.expire_all()
    u = db_session.query(User).filter(User.id == test_user.id).first()
    assert u.monthly_generations == 0
    assert u.purchased_generations == 5
    assert u.generations == 5


def test_vision_pipeline_dual_bucket_refund_on_unexpected_exception(client, auth_headers, test_user, db_session):
    """Vision generation refunds reserved balance when unexpected 500 exception occurs."""
    test_user.monthly_generations = 3
    test_user.purchased_generations = 2
    test_user.generations = 5
    db_session.commit()

    sample_b64 = base64.b64encode(b"valid_image_bytes_abc").decode("utf-8")

    with patch("server.campaigns.generate_omni_campaign_from_image", side_effect=RuntimeError("Internal GPU failure")):
        res = client.post(
            "/api/campaign/generate-vision",
            headers=auth_headers,
            json={"image_base64": sample_b64}
        )
        assert res.status_code == 500
        assert "Vision generation failed" in res.json()["detail"]

    # Invariant: Restored to monthly bucket
    db_session.expire_all()
    u = db_session.query(User).filter(User.id == test_user.id).first()
    assert u.monthly_generations == 3
    assert u.purchased_generations == 2
    assert u.generations == 5


def test_vision_pipeline_insufficient_generations_402(client, auth_headers, test_user, db_session):
    """Vision generation returns HTTP 402 Payment Required when total balance is 0."""
    test_user.monthly_generations = 0
    test_user.purchased_generations = 0
    test_user.generations = 0
    db_session.commit()

    sample_b64 = base64.b64encode(b"sample_image").decode("utf-8")
    res = client.post(
        "/api/campaign/generate-vision",
        headers=auth_headers,
        json={"image_base64": sample_b64}
    )
    assert res.status_code == 402
    assert "Insufficient campaigns" in res.json()["detail"]


# ============================================================================
# 5. VISION HELPER & PARSING RESILIENCE
# ============================================================================

def test_extract_clean_json_resilience():
    """_extract_clean_json extracts JSON with markdown fences, leading/trailing text, and regex fallback."""
    # 1. Clean JSON
    assert _extract_clean_json('{"key": "val"}') == {"key": "val"}
    
    # 2. Markdown fenced
    assert _extract_clean_json('```json\n{"key": "val"}\n```') == {"key": "val"}
    
    # 3. Leading and trailing chatter
    messy_text = 'Here is your response:\n```json\n{"title": "Product A", "count": 10}\n```\nHope this helps!'
    assert _extract_clean_json(messy_text) == {"title": "Product A", "count": 10}

    # 4. Invalid formatting raises ValueError
    with pytest.raises(ValueError, match="AI returned invalid campaign formatting"):
        _extract_clean_json("Not a json at all")


def test_generate_fallback_vision_campaign_structure_and_zero_emojis():
    """_generate_fallback_vision_campaign returns complete structure with zero emojis."""
    fb = _generate_fallback_vision_campaign("Ceramic Teapot", "Kitchenware")
    assert "Ceramic Teapot" in fb["detected_product_name"]
    assert len(fb["detected_description"]) > 20
    assert "title" in fb["blog_post"]
    assert "<h2>" in fb["blog_post"]["content"]
    assert len(fb["email_drip"]) == 3
    assert len(fb["social_posts"]) == 3
    assert len(EMOJI_PATTERN.findall(str(fb))) == 0


def test_generate_omni_campaign_from_image_offline_fallback():
    """generate_omni_campaign_from_image returns fallback when API keys are absent and allow_fallback=True."""
    with patch.dict(os.environ, {"GEMINI_API_KEY": "", "OPENAI_API_KEY": ""}):
        res = generate_omni_campaign_from_image(b"fake_image_bytes", "image/jpeg", "Leather Boots", "Winter collection", allow_fallback=True)
        assert "Leather Boots" in res["detected_product_name"]
        assert len(res["email_drip"]) == 3
        assert len(res["social_posts"]) == 3


@pytest.mark.parametrize("platform_key", ["amazon", "shopify", "etsy", "tiktok", "tiktok_shop", "ebay"])
def test_all_platforms_endpoint_integration(platform_key, client, auth_headers, test_user, db_session):
    """Tests that all supported platforms execute through the API and return valid MarketplaceOptimizeResponse."""
    res = client.post(
        "/api/optimizer/marketplace-listing",
        headers=auth_headers,
        json={
            "product_name": "Premium Bamboo Cutting Board",
            "platform": platform_key,
            "raw_details": "Organic bamboo with juice groove and side handles."
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["platform"] == platform_key
    assert len(data["optimized_title"]) > 0
    assert data["compliance_score"] >= 90
    assert len(EMOJI_PATTERN.findall(str(data))) == 0


def test_marketplace_optimizer_entitlement_gating(client, db_session):
    """Users without marketplace_optimizer_pack entitlement receive 403 Forbidden."""
    unentitled_user = User(
        id="user_unentitled_m1",
        email="unentitled@example.com",
        full_name="Unentitled User",
        hashed_password="hashed_dummy_password",
        plan="free",
        generations=10,
        monthly_generations=10,
        purchased_generations=0
    )
    db_session.add(unentitled_user)
    db_session.commit()

    token = create_access_token(unentitled_user.id, unentitled_user.email)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/api/optimizer/marketplace-listing",
        headers=headers,
        json={
            "product_name": "Bamboo Board",
            "platform": "amazon",
            "raw_details": "Organic bamboo cutting board."
        }
    )
    assert res.status_code == 403
    assert "Marketplace Listing Optimizer Pack" in res.json()["detail"]

