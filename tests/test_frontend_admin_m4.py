"""
test_frontend_admin_m4.py
Comprehensive Milestone 4 Test Suite covering:
1. Admin MRR/ARR Telemetry & Valuation Calculations (/admin/mrr-metrics, /api/admin/stats, admin.html)
2. Frontend Dashboard 18-Section Complete Markup & DOM Element ID Verifications (dashboard.html)
3. Dual-Bucket Quota Reservation & Atomic Refund Logic
4. Review Miner Dual-Bucket Quota Enforcement & Error Refund
5. Megastore BYOK Infrastructure Gating & Fernet Encryption
6. Stripe 503 Gateway Fault Tolerance on Unconfigured Keys
7. Multi-Tenant Scoping & Data Isolation
8. Zero-Emoji Compliance
"""

import os
import re
import json
import uuid
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from fastapi import HTTPException

from server.database import User, Subscription, RevenueRecord, InventoryItem, PriceMarginItem, BrandPersona, CustomerReview
from server.main import app, reserve_user_generations, refund_user_generations
from server.auth import hash_password, create_access_token, decrypt_credentials
import stripe

BASE_DIR = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# 1. Admin MRR/ARR Telemetry & Valuation Calculations
# ---------------------------------------------------------------------------
def test_admin_mrr_metrics_calculation(client, db_session):
    with patch("server.main.ADMIN_SECRET", "super-secret-m4-admin-key"):
        # Create test subscriptions
        user_bq = User(id="user-bq-1", email="bq@test.com", hashed_password="h", plan="boutique", is_active=True)
        user_std = User(id="user-std-1", email="std@test.com", hashed_password="h", plan="standard", is_active=True)
        user_mega = User(id="user-mega-1", email="mega@test.com", hashed_password="h", plan="megastore", is_active=True)
        user_canc = User(id="user-canc-1", email="canc@test.com", hashed_password="h", plan="boutique", is_active=True)

        db_session.add_all([user_bq, user_std, user_mega, user_canc])
        db_session.commit()

        sub_bq = Subscription(id="sub-1", user_id=user_bq.id, plan="boutique", status="active")
        sub_std = Subscription(id="sub-2", user_id=user_std.id, plan="standard", status="active")
        sub_mega = Subscription(id="sub-3", user_id=user_mega.id, plan="megastore", status="active")
        sub_canc = Subscription(id="sub-4", user_id=user_canc.id, plan="boutique", status="canceled")
        sub_past = Subscription(id="sub-5", user_id=user_bq.id, plan="boutique", status="past_due")

        rev1 = RevenueRecord(id="rev-1", user_id=user_bq.id, amount_cents=17949, type="subscription", status="succeeded")
        rev2 = RevenueRecord(id="rev-2", user_id=user_std.id, amount_cents=37949, type="subscription", status="succeeded")

        db_session.add_all([sub_bq, sub_std, sub_mega, sub_canc, sub_past, rev1, rev2])
        db_session.commit()

        res = client.get("/admin/mrr-metrics", headers={"x-admin-secret": "super-secret-m4-admin-key"})
        assert res.status_code == 200
        data = res.json()

        # Expected MRR = 179.49 + 379.49 + 9639.63 = 10198.61
        assert data["mrr_usd"] == 10198.61
        assert data["arr_usd"] == round(10198.61 * 12.0, 2)
        assert data["active_subscribers"] == 3
        assert data["canceled_subscribers"] == 1
        assert data["past_due_subscribers"] == 1
        assert data["software_asset_score"] is None
        assert data["valuation_estimate_usd"]["asset_sale_range"] == "$367,150 - $611,917"
        assert data["valuation_estimate_usd"]["arr_multiple_range"] == "3x - 5x ARR"
        assert data["active_subscribers_by_tier"]["boutique"] == 1
        assert data["active_subscribers_by_tier"]["standard"] == 1
        assert data["active_subscribers_by_tier"]["megastore"] == 1
        assert data["total_lifetime_revenue_usd"] == 558.98


def test_admin_auth_security(client):
    with patch("server.main.ADMIN_SECRET", "super-secret-m4-admin-key"):
        # Missing or invalid admin secret on MRR metrics
        res_no_auth = client.get("/admin/mrr-metrics")
        assert res_no_auth.status_code in [401, 403]

        res_bad_auth = client.get("/admin/mrr-metrics", headers={"x-admin-secret": "wrong-secret"})
        assert res_bad_auth.status_code in [401, 403]

        # Missing or invalid admin secret on Stats
        res_stats_bad = client.get("/api/admin/stats", headers={"x-admin-secret": "wrong-secret"})
        assert res_stats_bad.status_code == 401

        # Admin HTML Page serving
        res_page = client.get("/admin")
        assert res_page.status_code == 200
        assert "KopyKat Admin" in res_page.text
        assert "stat-mrr" in res_page.text
    assert "stat-arr" in res_page.text
    assert "stat-asset-score" in res_page.text
    assert "stat-valuation-asset" in res_page.text
    assert "stat-tier-megastore" in res_page.text


# ---------------------------------------------------------------------------
# 2. Frontend Dashboard 18-Section Complete Markup & DOM Element ID Verifications
# ---------------------------------------------------------------------------
def test_frontend_dashboard_sections_and_dom_ids():
    dash_path = BASE_DIR / "frontend" / "dashboard.html"
    assert dash_path.exists(), "dashboard.html must exist"
    content = dash_path.read_text(encoding="utf-8")

    # All 18 Sections Must Be Present
    expected_sections = [
        "section-overview",
        "section-generator",
        "section-omni",
        "section-apikeys",
        "section-usage",
        "section-billing",
        "section-docs",
        "section-bulk",
        "section-integrations",
        "section-miner",
        "section-inventory",
        "section-ugc",
        "section-pricing-monitor",
        "section-leads",
        "section-growth",
        "section-brand-persona",
        "section-listing-optimizer",
        "section-addons-store"
    ]

    for sec in expected_sections:
        assert f'id="{sec}"' in content, f"Section {sec} missing in dashboard.html"

    # Verify Key DOM Element IDs for Milestone 4
    m4_dom_ids = [
        # Competitor Miner
        "miner-product", "miner-competitor", "miner-reviews", "btn-mine-reviews",
        "miner-results-area", "miner-flaws-list", "miner-counter-desc", "miner-ad-hooks", "miner-comparison-body",
        # Inventory Balancer
        "inv-webhook-url", "inv-sku", "inv-title", "inv-qty", "inv-table-body", "inv-logs-list",
        # UGC & Reviews
        "ugc-prod", "ugc-tone", "ugc-incentive", "btn-gen-ugc-drip", "ugc-drip-results", "ugc-drip-cards", "ugc-reviews-list",
        # Price Monitor
        "pm-sku", "pm-title", "pm-cogs", "pm-retail", "pm-comp", "pm-target", "pm-table-body",
        # Leads & Growth
        "leads-feed-list", "stat-seo-posts", "stat-seo-words", "stat-drips-sent", "stat-paid-subscribers",
        # Persona
        "persona-brand-name", "persona-voice-tone", "persona-audience", "persona-guidelines", "persona-sample", "persona-status",
        # Marketplace Optimizer
        "opt-platform", "opt-product-name", "opt-raw-details", "opt-keywords", "opt-audience",
        "optimizer-results-card", "opt-score-badge", "optimizer-results-content",
        # Addons Store & BYOK
        "addons-grid", "byok-provider", "byok-key-input", "byok-status"
    ]

    for elem_id in m4_dom_ids:
        assert f'id="{elem_id}"' in content, f"DOM ID '{elem_id}' missing in dashboard.html"

    # Verify line 370 button text clean fix
    assert "?? Generate Copy" not in content
    assert "Generate Copy" in content


# ---------------------------------------------------------------------------
# 3. Dual-Bucket Quota Reservation & Atomic Refund Logic
# ---------------------------------------------------------------------------
def test_dual_bucket_quota_ledger(db_session):
    user = User(
        id="user-quota-test",
        email="quota@test.com",
        hashed_password="hash",
        plan="boutique",
        generations=15,
        monthly_generations=5,
        purchased_generations=10,
        is_active=True
    )
    db_session.add(user)
    db_session.commit()

    # Step 1: Reserve 3 generations (monthly has 5 -> uses 3 monthly, 0 purchased)
    m_used, p_used = reserve_user_generations(user.id, 3, db_session)
    assert m_used == 3
    assert p_used == 0
    db_session.refresh(user)
    assert user.monthly_generations == 2
    assert user.purchased_generations == 10
    assert user.generations == 12

    # Step 2: Reserve 4 generations (monthly has 2 -> uses 2 monthly, 2 purchased)
    m_used2, p_used2 = reserve_user_generations(user.id, 4, db_session)
    assert m_used2 == 2
    assert p_used2 == 2
    db_session.refresh(user)
    assert user.monthly_generations == 0
    assert user.purchased_generations == 8
    assert user.generations == 8

    # Step 3: Refund the second reservation atomically
    refund_user_generations(user.id, m_used2, p_used2, db_session)
    db_session.refresh(user)
    assert user.monthly_generations == 2
    assert user.purchased_generations == 10
    assert user.generations == 12

    # Step 4: Exceed available total generations -> must raise HTTP 402
    with pytest.raises(HTTPException) as exc_info:
        reserve_user_generations(user.id, 50, db_session)
    assert exc_info.value.status_code == 402


# ---------------------------------------------------------------------------
# 4. Review Miner Dual-Bucket Quota Enforcement & Error Refund
# ---------------------------------------------------------------------------
def test_competitor_review_mining_dual_bucket_and_refund(client, db_session, test_user, auth_headers):
    test_user.generations = 10
    test_user.monthly_generations = 5
    test_user.purchased_generations = 5
    db_session.commit()

    mock_analysis = {
        "extracted_flaws": ["Uncomfortable seat padding", "Weak armrests"],
        "counter_description": "Engineered with high-density aerospace memory foam.",
        "comparison_points": [{"aspect": "Padding", "competitor_flaw": "Thin foam", "our_advantage": "Aerospace memory foam"}],
        "ad_hooks": ["Tired of sore hips after 2 hours?"]
    }

    # Successful call: deductions occur
    with patch("server.ai_engine.mine_competitor_reviews", new_callable=AsyncMock, return_value=mock_analysis):
        res = client.post("/api/competitor/mine-reviews", headers=auth_headers, json={
            "product_name": "Lumina Chair",
            "competitor_name": "GenericBrand",
            "reviews_text": "The chair seat padding is completely flat and hurts after one hour."
        })
        assert res.status_code == 200
        data = res.json()
        assert data["product_name"] == "Lumina Chair"
        assert len(data["extracted_flaws"]) == 2

        db_session.refresh(test_user)
        assert test_user.monthly_generations == 4
        assert test_user.generations == 9

    # Failed call: exception raised in AI engine -> atomic credit refund occurs
    with patch("server.ai_engine.mine_competitor_reviews", new_callable=AsyncMock, side_effect=RuntimeError("AI Provider Timeout")):
        res_fail = client.post("/api/competitor/mine-reviews", headers=auth_headers, json={
            "product_name": "Lumina Chair",
            "competitor_name": "GenericBrand",
            "reviews_text": "The chair seat padding is completely flat and hurts after one hour."
        })
        assert res_fail.status_code == 500

        db_session.refresh(test_user)
        # Verify credits were restored back to 4 monthly / 9 total
        assert test_user.monthly_generations == 4
        assert test_user.generations == 9


# ---------------------------------------------------------------------------
# 5. Megastore BYOK Infrastructure Gating & Fernet Encryption
# ---------------------------------------------------------------------------
def test_byok_megastore_gating_and_encryption(client, db_session, test_user, auth_headers):
    # Non-Megastore user (Boutique) attempts BYOK
    test_user.plan = "boutique"
    db_session.commit()

    res_blocked = client.post("/api/user/custom-ai-key", headers=auth_headers, json={
        "api_key": "sk-proj-testkey123456789",
        "provider": "openai"
    })
    assert res_blocked.status_code == 403
    assert "Megastore" in res_blocked.json()["detail"]

    # Upgrade user to Megastore
    test_user.plan = "megastore"
    db_session.commit()

    res_success = client.post("/api/user/custom-ai-key", headers=auth_headers, json={
        "api_key": "sk-proj-megastore-secret-key-999",
        "provider": "openai"
    })
    assert res_success.status_code == 200
    assert res_success.json()["success"] is True

    # Verify Fernet encryption at rest in DB
    db_session.refresh(test_user)
    assert test_user.custom_ai_key_encrypted is not None
    assert test_user.custom_ai_key_encrypted != "sk-proj-megastore-secret-key-999"
    decrypted = decrypt_credentials(test_user.custom_ai_key_encrypted)
    assert decrypted == "sk-proj-megastore-secret-key-999"

    # Verify status endpoint
    res_status = client.get("/api/user/custom-ai-key", headers=auth_headers)
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["has_custom_key"] is True
    assert status_data["unlimited_active"] is True
    assert status_data["provider"] == "openai"


# ---------------------------------------------------------------------------
# 6. Stripe 503 Gateway Fault Tolerance on Unconfigured Keys
# ---------------------------------------------------------------------------
def test_stripe_503_on_unconfigured_gateway(client, auth_headers):
    # Ensure stripe.api_key is empty/unconfigured
    original_key = stripe.api_key
    stripe.api_key = None

    try:
        res = client.post("/billing/addon/checkout", headers=auth_headers, json={
            "addon_key": "brand_voice_training"
        })
        assert res.status_code == 503
        assert "Stripe is not configured" in res.json()["detail"] or "Payment gateway" in res.json()["detail"]
    finally:
        stripe.api_key = original_key


# ---------------------------------------------------------------------------
# 7. Multi-Tenant Scoping & Data Isolation
# ---------------------------------------------------------------------------
def test_multi_tenant_isolation(client, db_session, test_user, auth_headers):
    # Create Tenant B
    user_b = User(
        id="user-b-tenant-id",
        email="tenantb@example.com",
        hashed_password=hash_password("Pass123!"),
        plan="boutique",
        generations=10,
        is_active=True
    )
    db_session.add(user_b)
    db_session.commit()

    token_b = create_access_token(user_b.id, user_b.email)
    auth_headers_b = {"Authorization": f"Bearer {token_b}"}

    # Tenant A creates an inventory item and a price item
    client.post("/api/inventory/item", headers=auth_headers, json={
        "sku": "TENANT-A-SKU",
        "title": "Tenant A Exclusive Item",
        "total_stock": 100
    })
    client.post("/api/pricing/item", headers=auth_headers, json={
        "sku": "TENANT-A-PRICING",
        "product_name": "Tenant A Secret Margin",
        "cogs_usd": 10.0,
        "selling_price_usd": 30.0
    })

    # Tenant B queries inventory and pricing -> MUST NOT see Tenant A's items
    res_inv_b = client.get("/api/inventory", headers=auth_headers_b)
    assert res_inv_b.status_code == 200
    assert len(res_inv_b.json()) == 0

    res_pm_b = client.get("/api/pricing/items", headers=auth_headers_b)
    assert res_pm_b.status_code == 200
    assert len(res_pm_b.json()) == 0


# ---------------------------------------------------------------------------
# 8. Zero-Emoji Compliance
# ---------------------------------------------------------------------------
def test_zero_emojis_in_frontend():
    # Emoji detection pattern for unicode emoji ranges
    emoji_pattern = re.compile(
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

    for filename in ["frontend/dashboard.html", "frontend/admin.html"]:
        file_path = BASE_DIR / filename
        assert file_path.exists()
        text = file_path.read_text(encoding="utf-8")
        matches = emoji_pattern.findall(text)
        assert len(matches) == 0, f"Found emojis {matches} in {filename}"
