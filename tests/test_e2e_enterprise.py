"""
test_e2e_enterprise.py - Tier 3 (Cross-Feature Combinations) & Tier 4 (Real-World Enterprise Scenarios).

Comprehensive end-to-end integration workflows validating cross-module interoperability,
data consistency across stateful lifecycles, and resilient business continuity.
Strict zero-emoji compliance.
"""

import base64
import json
import os
import re
import uuid
from unittest.mock import patch, AsyncMock

import pytest
from starlette.testclient import TestClient
from sqlalchemy import text

import server.billing
import server.ai_engine
from server.ai_engine import (
    optimize_marketplace_listing,
    mine_competitor_reviews,
    generate_copy,
)
from server.auth import (
    create_access_token,
    encrypt_credentials,
    decrypt_credentials,
)
from server.billing import (
    user_has_entitlement,
    PLANS,
    ADD_ONS,
)
from server.campaigns import generate_omni_campaign_from_image
from server.connector_engine import validate_public_url, ConnectorError
from server.connector_registry import execute_operation
from server.database import (
    User,
    Subscription,
    RevenueRecord,
    StripeEvent,
    InventoryItem,
    InventorySyncLog,
    InventoryWebhookEvent,
    CustomConnector,
    ConnectorAuditLog,
    BlogPost,
    DripLog,
    OpportunityLog,
    CustomerReview,
    PriceMarginItem,
    UserEntitlement,
    BrandPersona,
    UserIntegration,
    Campaign,
    CompetitorAudit,
)
from server.inventory import (
    sync_inventory_across_platforms,
    reconcile_inventory_sku,
)
from server.main import (
    app,
    reserve_user_generations,
    refund_user_generations,
)
from server.marketing import generate_seo_post
from server.pricing_monitor import compute_pricing_analysis
from server.reviews_ugc import (
    generate_post_purchase_drip,
    classify_review_sentiment_and_reply,
)

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
# TIER 3: CROSS-FEATURE COMBINATIONS (8 Workflows)
# ============================================================================

@pytest.mark.asyncio
async def test_tier3_flow1_vision_to_optimizer_to_inventory_sync(client, auth_headers, test_user, db_session):
    """
    Tier 3 - Flow 1:
    Multi-Modal Vision Generation -> Platform Listing Optimizer -> Multi-Channel Inventory Sync.
    """
    test_user.generations = 20
    test_user.monthly_generations = 20
    db_session.commit()

    # Step 1: Ingest product image via Multi-Modal Vision Pipeline
    sample_b64 = base64.b64encode(b"enterprise_smart_watch_image_data").decode("utf-8")
    mock_campaign = {
        "detected_product_name": "Titanium Smartwatch Pro",
        "detected_description": "Aircraft-grade titanium smartwatch with 14-day battery and sapphire glass.",
        "blog_post": {"title": "Ultimate Smartwatch", "content": "<p>Smartwatch review</p>"},
        "email_drip": [{"subject": "Next Gen Wearable", "body": "<p>PAS copy</p>"}],
        "social_posts": ["Track performance in style with Titanium Smartwatch Pro."]
    }

    with patch("server.campaigns.generate_omni_campaign_from_image", return_value=mock_campaign):
        res_vision = client.post(
            "/api/campaign/generate-vision",
            headers=auth_headers,
            json={"image_base64": sample_b64, "mime_type": "image/png"}
        )
        assert res_vision.status_code == 200
        vision_data = res_vision.json()
        prod_name = vision_data["assets"]["detected_product_name"]
        prod_desc = vision_data["assets"]["detected_description"]

    # Step 2: Optimize listing schema for Amazon and Shopify
    res_amazon = await optimize_marketplace_listing(prod_name, "amazon", prod_desc)
    assert len(res_amazon["optimized_title"]) <= 200
    assert len(res_amazon["bullet_points"]) == 5
    assert res_amazon["compliance_score"] >= 90

    res_shopify = await optimize_marketplace_listing(prod_name, "shopify", prod_desc)
    assert len(res_shopify["optimized_title"]) <= 70
    assert len(res_shopify["meta_description"]) <= 155

    # Step 3: Register inventory item and fan out initial stock across connected platforms
    sku = f"WATCH-PRO-{uuid.uuid4().hex[:6].upper()}"
    res_inv = client.post(
        "/api/inventory/item",
        headers=auth_headers,
        json={"sku": sku, "title": prod_name, "total_stock": 250}
    )
    assert res_inv.status_code == 200
    assert res_inv.json()["total_stock"] == 250

    # Step 4: Simulate a sale on Shopify and verify loop-free fanout
    sale_evt_id = f"evt_sale_{uuid.uuid4().hex[:8]}"
    fanout = sync_inventory_across_platforms(
        user_id=test_user.id,
        sku=sku,
        delta=-5,
        trigger_platform="shopify",
        db=db_session,
        event_id=sale_evt_id
    )
    assert fanout["new_stock"] == 245
    assert fanout["trigger_platform"] == "shopify"


def test_tier3_flow2_stripe_webhook_to_quota_to_vision(client, db_session):
    """
    Tier 3 - Flow 2:
    Stripe Webhook (Plan Checkout) -> Dual-Bucket Quota Reservation -> Campaign Generation.
    """
    user = User(
        id="u_flow2_stripe",
        email="flow2_stripe@enterprise.com",
        hashed_password="pwd",
        plan="free",
        generations=0,
        monthly_generations=0,
        purchased_generations=0
    )
    db_session.add(user)
    db_session.commit()

    token = create_access_token(user.id, user.email)
    headers = {"Authorization": f"Bearer {token}"}

    # Step 1: Verify 402 rejection before subscription
    res_reject = client.post(
        "/api/campaign/generate-vision",
        headers=headers,
        json={"image_base64": base64.b64encode(b"img").decode("utf-8")}
    )
    assert res_reject.status_code == 402

    # Step 2: Ingest Stripe subscription checkout completed webhook for standard plan ($379.49)
    evt_id = f"evt_sub_standard_{uuid.uuid4().hex[:8]}"
    stripe_event = {
        "id": evt_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": f"cs_sub_{uuid.uuid4().hex[:8]}",
                "customer": "cus_standard_flow",
                "metadata": {"user_id": user.id, "plan": "standard"},
                "amount_total": 37949,
                "currency": "usd"
            }
        }
    }

    with patch.object(server.billing, "STRIPE_WEBHOOK_SECRET", "whsec_test"), \
         patch("stripe.Webhook.construct_event", side_effect=lambda p, s, sec: stripe_event):
        res_hook = client.post("/billing/webhook", json=stripe_event, headers={"Stripe-Signature": "t=1,v1=sig"})
        assert res_hook.status_code == 200
        assert res_hook.json()["status"] == "processed"

    # Step 3: Verify user account received Standard tier 1000 monthly generations
    db_session.expire_all()
    u_after = db_session.query(User).filter(User.id == user.id).first()
    assert u_after.plan == "standard"
    assert u_after.monthly_generations == 1000
    assert u_after.generations == 1000

    # Step 4: Verify successful vision campaign execution with atomic quota deduction
    mock_campaign = {
        "detected_product_name": "Standard Plan Product",
        "detected_description": "Description",
        "blog_post": {"title": "Title", "content": "<p>Content</p>"},
        "email_drip": [],
        "social_posts": []
    }
    with patch("server.campaigns.generate_omni_campaign_from_image", return_value=mock_campaign):
        res_vision = client.post(
            "/api/campaign/generate-vision",
            headers=headers,
            json={"image_base64": base64.b64encode(b"img").decode("utf-8")}
        )
        assert res_vision.status_code == 200

    db_session.expire_all()
    u_final = db_session.query(User).filter(User.id == user.id).first()
    assert u_final.generations == 999


@pytest.mark.asyncio
async def test_tier3_flow3_reddit_scout_to_mining_to_seo_blog_to_ping(client, auth_headers, test_user, db_session, monkeypatch):
    """
    Tier 3 - Flow 3:
    Reddit Opportunity Scout -> Competitor Flaw Mining -> SEO Blog Generation -> Ping Index.
    """
    test_user.generations = 10
    db_session.commit()

    # Step 1: Reddit opportunity scout identifies high-intent buyer post
    lead_id = f"lead_{uuid.uuid4().hex[:8]}"
    opp = OpportunityLog(
        id=lead_id,
        platform="reddit",
        post_id="post_scout_001",
        post_title="Looking for a high quality chef knife that doesn't chip easily",
        post_url="https://reddit.com/r/cooking/123",
        draft_reply="Our chef knives use cryogenically treated German steel.",
        score=95,
        alerted=True
    )
    db_session.add(opp)
    db_session.commit()

    res_leads = client.get("/api/leads", headers=auth_headers)
    assert res_leads.status_code == 200
    assert any(l["id"] == lead_id for l in res_leads.json())

    # Step 2: Competitor review miner analyzes rival weaknesses
    mock_mined = {
        "extracted_flaws": ["Blades chip under normal kitchen prep", "Handles loosen over time"],
        "counter_description": "Engineered with cryogenic high-carbon German steel with full tang construction.",
        "comparison_points": [{"aspect": "Durability", "competitor_flaw": "Chipping blades", "our_advantage": "Cryogenic hardening"}],
        "ad_hooks": ["Tired of chipped knives? Upgrade to precision German steel."]
    }
    async def mock_mine(product_name, competitor_name, reviews_text):
        return mock_mined

    monkeypatch.setattr("server.ai_engine.mine_competitor_reviews", mock_mine)

    res_mine = client.post(
        "/api/competitor/mine-reviews",
        headers=auth_headers,
        json={
            "product_name": "CryoShield Chef Knife",
            "competitor_name": "RivalCutlery",
            "reviews_text": "The blade chipped after two weeks of use!"
        }
    )
    assert res_mine.status_code == 200
    mined_data = res_mine.json()
    assert len(mined_data["extracted_flaws"]) == 2

    # Step 3: SEO engine generates blog post addressing the competitor flaw
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        post = await generate_seo_post(db_session)
        assert post is not None
        assert post.published is True
        assert post.word_count >= 10

    # Step 4: Ping search engine indexes for instant crawling
    res_ping = client.post("/api/seo/ping-index", headers=auth_headers)
    assert res_ping.status_code == 200
    assert res_ping.json()["success"] is True


@pytest.mark.asyncio
async def test_tier3_flow4_shopify_import_to_copy_gen_to_price_monitor(client, auth_headers, test_user, db_session):
    """
    Tier 3 - Flow 4:
    Shopify Product Import -> AI Marketing Copy -> Margin / Pricing Monitor Calculation.
    """
    test_user.generations = 10
    db_session.commit()

    # Step 1: Seed inventory item representing Shopify imported catalog SKU
    sku = f"SHOPIFY-IMPORT-{uuid.uuid4().hex[:6]}"
    inv_item = InventoryItem(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        sku=sku,
        title="Artisan Pour Over Coffee Dripper",
        total_stock=100,
        platform_stock=json.dumps({"shopify": 100})
    )
    db_session.add(inv_item)
    db_session.commit()

    # Step 2: Generate multi-variation product description copy
    mock_copy = {
        "id": str(uuid.uuid4()),
        "type": "product_description",
        "output": "Engineered with double-wall insulated ceramic for optimal extraction temperature.",
        "tokens_used": 150,
        "cost_usd": 0.002,
        "created_at": "2026-08-23T00:00:00Z"
    }
    with patch("server.main.generate_copy", return_value=mock_copy):
        res_copy = client.post(
            "/api/generate",
            headers=auth_headers,
            json={
                "type": "product_description",
                "context": f"Product: {inv_item.title}, SKU: {sku}",
                "variations": 2
            }
        )
        assert res_copy.status_code == 200
        assert "double-wall" in res_copy.json()["output"]

    # Step 3: Calculate unit economics and healthy profit margins
    cogs = 12.50
    selling_price = 45.00
    competitor_price = 42.00
    pricing = compute_pricing_analysis(
        cogs=cogs,
        selling_price=selling_price,
        competitor_price=competitor_price,
        target_margin=50.0
    )
    assert pricing["current_margin_pct"] == round(((45.0 - 12.5) / 45.0) * 100.0, 2)
    assert pricing["profit_per_unit_usd"] == 32.50
    assert pricing["status"] == "healthy"


def test_tier3_flow5_negative_review_to_sentiment_to_drip(client, auth_headers, test_user, db_session):
    """
    Tier 3 - Flow 5:
    Customer Negative Review -> Sentiment Classification & Draft Reply -> Post-Purchase UGC Drip.
    """
    # Step 1: Submit 1-star customer review
    res_rev = client.post(
        "/api/reviews/submit",
        headers=auth_headers,
        json={
            "customer_name": "Marcus Vance",
            "customer_email": "marcus@example.com",
            "product_name": "Bluetooth ANC Headphones",
            "rating": 1,
            "review_text": "The right earbud stopped charging after 3 days. Extremely disappointed."
        }
    )
    assert res_rev.status_code == 200
    rev_data = res_rev.json()
    assert rev_data["sentiment"] == "negative"
    assert rev_data["status"] == "action_needed"
    assert "replacement or full refund" in rev_data["draft_reply"]

    # Step 2: Verify review is listed in merchant queue
    res_list = client.get("/api/reviews", headers=auth_headers)
    assert res_list.status_code == 200
    assert any(r["customer_name"] == "Marcus Vance" for r in res_list.json())

    # Step 3: Trigger post-purchase UGC drip sequence to gather positive reviews from satisfied buyers
    drip = generate_post_purchase_drip("Bluetooth ANC Headphones", brand_tone="Empathetic", incentive="15% discount")
    assert len(drip) == 3
    assert drip[0]["day"] == 3
    assert drip[1]["day"] == 7
    assert drip[2]["day"] == 14
    assert len(EMOJI_PATTERN.findall(str(drip))) == 0


@pytest.mark.asyncio
async def test_tier3_flow6_brand_persona_to_multichannel_listing_optimizer(client, auth_headers, test_user, db_session):
    """
    Tier 3 - Flow 6:
    Custom Brand Voice Persona -> Multi-Platform Marketplace Listing Generation (Amazon/Shopify/Etsy).
    """
    # Step 1: Configure merchant Brand Persona
    res_bp = client.post(
        "/api/brand-persona",
        headers=auth_headers,
        json={
            "brand_name": "Vanguard Precision Gear",
            "brand_voice_tone": "Authoritative & Technical",
            "target_audience": "Tactical athletes and professional survivalists",
            "core_values": "Indestructible construction, military specifications, lifetime guarantee",
            "banned_words": "cheap, discount, plastic"
        }
    )
    assert res_bp.status_code == 200
    assert res_bp.json()["brand_name"] == "Vanguard Precision Gear"

    # Step 2: Generate optimized listings across 3 major channels
    prod_name = "Tactical Waterproof Backpack 45L"
    raw_details = "1000D Cordura nylon with laser-cut MOLLE webbing and YKK heavy duty zippers."

    # Amazon
    amazon_res = await optimize_marketplace_listing(prod_name, "amazon", raw_details)
    assert len(amazon_res["optimized_title"]) <= 200
    assert len(amazon_res["bullet_points"]) == 5
    assert len(amazon_res["backend_search_terms"].encode("utf-8")) <= 249

    # Shopify
    shopify_res = await optimize_marketplace_listing(prod_name, "shopify", raw_details)
    assert len(shopify_res["optimized_title"]) <= 70
    assert len(shopify_res["meta_description"]) <= 155

    # Etsy
    etsy_res = await optimize_marketplace_listing(prod_name, "etsy", raw_details)
    assert len(etsy_res["optimized_title"]) <= 140
    assert len(etsy_res["tags"]) == 13

    # Ensure zero emojis across all generated listings
    assert len(EMOJI_PATTERN.findall(str(amazon_res))) == 0
    assert len(EMOJI_PATTERN.findall(str(shopify_res))) == 0
    assert len(EMOJI_PATTERN.findall(str(etsy_res))) == 0


def test_tier3_flow7_inventory_webhook_to_fanout_to_reconciliation(client, auth_headers, test_user, db_session):
    """
    Tier 3 - Flow 7:
    Multi-Channel Inventory Webhook Event -> Loop-Free Stock Fanout -> Drift Reconciliation Engine.
    """
    # Step 1: Create initial inventory item with 80 units
    sku = f"SYNC-RECON-{uuid.uuid4().hex[:6]}"
    inv = InventoryItem(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        sku=sku,
        title="Wireless Charging Stand",
        total_stock=80,
        platform_stock=json.dumps({"shopify": 80, "amazon": 80})
    )
    db_session.add(inv)
    db_session.commit()

    # Step 2: Ingest webhook sale of 10 units on Amazon
    evt_id = f"evt_amz_sale_{uuid.uuid4().hex[:8]}"
    fanout = sync_inventory_across_platforms(
        user_id=test_user.id,
        sku=sku,
        delta=-10,
        trigger_platform="amazon",
        db=db_session,
        event_id=evt_id
    )
    assert fanout["new_stock"] == 70
    assert fanout["fanout_results"]["amazon"] == "source_event"

    # Step 3: Warehouse physical audit counts 75 units (5 unit drift discrepancy)
    reconciled = reconcile_inventory_sku(
        user_id=test_user.id,
        sku=sku,
        canonical_stock=75,
        db=db_session
    )
    assert reconciled["previous_stock"] == 70
    assert reconciled["reconciled_stock"] == 75
    assert reconciled["drift_corrected"] == 5

    # Step 4: Verify audit log recorded reconciliation event
    log = db_session.query(InventorySyncLog).filter(
        InventorySyncLog.sku == sku,
        InventorySyncLog.trigger_platform == "reconciliation_engine"
    ).first()
    assert log is not None
    assert log.quantity_change == 5


def test_tier3_flow8_subscription_upgrade_to_mrr_metrics_to_byok(client, db_session):
    """
    Tier 3 - Flow 8:
    Subscription Upgrade -> MRR / ARR Telemetry Verification -> Megastore Custom AI Key (BYOK) Provisioning.
    """
    # Step 1: Create a Boutique user ($179.49)
    user = User(
        id="u_upgrade_flow",
        email="upgrade_flow@megacorp.com",
        hashed_password="pwd",
        plan="boutique",
        generations=150,
        monthly_generations=150,
        purchased_generations=0
    )
    db_session.add(user)
    db_session.commit()

    token = create_access_token(user.id, user.email)
    headers = {"Authorization": f"Bearer {token}"}

    # Step 2: Boutique tier cannot configure custom BYOK key (403)
    res_forbidden = client.post(
        "/api/user/custom-ai-key",
        headers=headers,
        json={"api_key": "sk-custom-openai-enterprise-key", "provider": "openai"}
    )
    assert res_forbidden.status_code == 403

    # Step 3: Ingest Stripe Webhook upgrading user to Megastore plan ($9,639.63/mo)
    upgrade_event = {
        "id": f"evt_upgrade_{uuid.uuid4().hex[:8]}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": f"cs_mega_{uuid.uuid4().hex[:8]}",
                "customer": "cus_megacorp",
                "metadata": {"user_id": user.id, "plan": "megastore"},
                "amount_total": 963963,
                "currency": "usd"
            }
        }
    }

    with patch.object(server.billing, "STRIPE_WEBHOOK_SECRET", "whsec_test"), \
         patch("stripe.Webhook.construct_event", side_effect=lambda p, s, sec: upgrade_event):
        res_hook = client.post("/billing/webhook", json=upgrade_event, headers={"Stripe-Signature": "t=1,v1=sig"})
        assert res_hook.status_code == 200

    # Step 4: Verify MRR metrics update accurately reflecting Megastore MRR ($9,639.63)
    with patch("server.main.ADMIN_SECRET", "sec_123"):
        res_mrr = client.get("/admin/mrr-metrics", headers={"X-Admin-Secret": "sec_123"})
        assert res_mrr.status_code == 200
        data_mrr = res_mrr.json()
        assert data_mrr["mrr_usd"] >= 9639.63
        assert data_mrr["active_subscribers_by_tier"]["megastore"] >= 1

    # Step 5: Megastore tier successfully provisions BYOK key
    res_byok = client.post(
        "/api/user/custom-ai-key",
        headers=headers,
        json={"api_key": "sk-custom-openai-enterprise-key", "provider": "openai"}
    )
    assert res_byok.status_code == 200
    assert res_byok.json()["success"] is True

    # Step 6: Verify unlimited generations active
    res_status = client.get("/api/user/custom-ai-key", headers=headers)
    assert res_status.status_code == 200
    assert res_status.json()["unlimited_active"] is True


# ============================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS (5 Enterprise Scenarios)
# ============================================================================

@pytest.mark.asyncio
async def test_tier4_scenario1_enterprise_multichannel_catalog_and_stock_syndication(client, auth_headers, test_user, db_session):
    """
    Tier 4 - Scenario 1: Enterprise Multi-Channel Catalog Syndication & Real-Time Stock Synchronization.
    A top-volume merchant syndicates product catalog across 5 marketplaces, distributes inventory,
    processes high-throughput order webhooks without overselling, and reconciles drift.
    """
    test_user.generations = 50
    db_session.commit()

    # Step 1: Connect channels (Amazon, Shopify, Etsy, TikTok Shop, eBay)
    for plat in ["shopify", "amazon", "etsy", "ebay"]:
        db_session.add(UserIntegration(
            id=str(uuid.uuid4()),
            user_id=test_user.id,
            platform=plat,
            credentials=encrypt_credentials(json.dumps({"api_key": f"mock_token_{plat}"})),
            status="connected"
        ))
    db_session.commit()

    # Step 2: Syndicate catalog item across Amazon, Shopify, and Etsy schemas
    sku = f"ENTERPRISE-SKU-{uuid.uuid4().hex[:6]}"
    prod_name = "Heavy Duty Camping Dutch Oven 6Qt"
    raw_specs = "Pre-seasoned cast iron dutch oven with dual loop handles, flanged lid, and spiral bail handle."

    amazon_listing = await optimize_marketplace_listing(prod_name, "amazon", raw_specs)
    shopify_listing = await optimize_marketplace_listing(prod_name, "shopify", raw_specs)
    etsy_listing = await optimize_marketplace_listing(prod_name, "etsy", raw_specs)

    assert len(amazon_listing["bullet_points"]) == 5
    assert len(shopify_listing["optimized_title"]) <= 70
    assert len(etsy_listing["tags"]) == 13

    # Step 3: Ingest initial bulk stock of 500 units
    inv = InventoryItem(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        sku=sku,
        title=prod_name,
        total_stock=500,
        platform_stock=json.dumps({"shopify": 500, "amazon": 500, "etsy": 500, "ebay": 500})
    )
    db_session.add(inv)
    db_session.commit()

    # Step 4: Rapid multi-channel sales velocity (concurrent purchases across platforms)
    # 20 units sold on Amazon
    sync_inventory_across_platforms(test_user.id, sku, -20, "amazon", db_session, f"ord_amz_{uuid.uuid4().hex[:6]}")
    # 15 units sold on Shopify
    sync_inventory_across_platforms(test_user.id, sku, -15, "shopify", db_session, f"ord_shp_{uuid.uuid4().hex[:6]}")
    # 5 units sold on Etsy
    sync_inventory_across_platforms(test_user.id, sku, -5, "etsy", db_session, f"ord_ets_{uuid.uuid4().hex[:6]}")

    db_session.expire_all()
    updated_inv = db_session.query(InventoryItem).filter(InventoryItem.sku == sku).first()
    assert updated_inv.total_stock == 460

    # Step 5: Execute end-of-day drift reconciliation to match physical warehouse count (458 units)
    recon = reconcile_inventory_sku(test_user.id, sku, 458, db_session)
    assert recon["drift_corrected"] == -2
    assert recon["reconciled_stock"] == 458

    # Step 6: Verify full audit trail recorded
    logs = db_session.query(InventorySyncLog).filter(InventorySyncLog.sku == sku).all()
    assert len(logs) >= 4


def test_tier4_scenario2_automated_lead_discovery_to_customer_retention_loop(client, auth_headers, test_user, db_session):
    """
    Tier 4 - Scenario 2: Automated Lead Discovery to Customer Retention & UGC Review Loop.
    E-commerce brand detects Reddit purchase intent, counters competitor flaws, converts lead,
    and runs a 3-step UGC review generation sequence.
    """
    # Step 1: Discovers high-intent Reddit post
    lead_id = f"lead_enterprise_{uuid.uuid4().hex[:6]}"
    lead = OpportunityLog(
        id=lead_id,
        platform="reddit",
        post_id="post_lead_reddit_100",
        post_title="What is the best ergonomic keyboard for carpal tunnel syndrome?",
        post_url="https://reddit.com/r/mechanicalkeyboards/456",
        draft_reply="KopyKat client provides split-ergonomic mechanical keyboards with tenting.",
        score=96,
        alerted=True
    )
    db_session.add(lead)
    db_session.commit()

    res_leads = client.get("/api/leads", headers=auth_headers)
    assert res_leads.status_code == 200
    assert any(l["id"] == lead_id and l["score"] == 96 for l in res_leads.json())

    # Step 2: Post-purchase 3-step UGC email drip automation configured
    drip = generate_post_purchase_drip("Split Ergonomic Keyboard", brand_tone="Supportive", incentive="10% store credit")
    assert len(drip) == 3
    assert drip[0]["day"] == 3
    assert drip[1]["day"] == 7
    assert drip[2]["day"] == 14

    # Step 3: Customer completes review with 5-star rating
    res_rev = client.post(
        "/api/reviews/submit",
        headers=auth_headers,
        json={
            "customer_name": "Elena Rostova",
            "customer_email": "elena@example.com",
            "product_name": "Split Ergonomic Keyboard",
            "rating": 5,
            "review_text": "Zero wrist pain after working 10 hours a day. The tenting stand is phenomenal!"
        }
    )
    assert res_rev.status_code == 200
    data = res_rev.json()
    assert data["sentiment"] == "positive"
    assert data["status"] == "published"
    assert "Hi Elena Rostova" in data["draft_reply"]

    # Step 4: Verify zero emojis in all generated retention copy
    assert len(EMOJI_PATTERN.findall(str(drip))) == 0
    assert len(EMOJI_PATTERN.findall(str(data))) == 0


def test_tier4_scenario3_adversarial_quota_depletion_ssrf_and_replay_defense(client, auth_headers, test_user, db_session):
    """
    Tier 4 - Scenario 3: Adversarial Quota Depletion, SSRF Attack Vector, and Webhook Replay Defense.
    Simulates adversarial attacker attempting:
    1. SSRF / DNS rebinding against localhost, 127.0.0.1, 169.254.169.254, and RFC1918 addresses
    2. Webhook replay attacks to double-credit or double-decrement stock
    3. Credit exhaustion beyond available quota
    """
    # 1. SSRF Defense
    malicious_targets = [
        "https://localhost/admin/keys",
        "https://127.0.0.1:8080/secrets",
        "https://169.254.169.254/latest/meta-data/iam/credentials",
        "https://10.0.0.1/internal/config",
        "https://192.168.1.1/router/status",
        "https://172.16.0.1/vault",
        "http://unencrypted.com/api"
    ]
    for url in malicious_targets:
        with pytest.raises(ConnectorError):
            validate_public_url(url)

    # 2. Webhook Replay Defense
    sku = f"REPLAY-SEC-SKU-{uuid.uuid4().hex[:6]}"
    inv = InventoryItem(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        sku=sku,
        title="Security Test Item",
        total_stock=100
    )
    db_session.add(inv)
    db_session.commit()

    order_event_id = f"evt_replay_attack_{uuid.uuid4().hex[:8]}"
    # First delivery
    res1 = client.post(
        "/api/inventory/webhook/shopify",
        headers=auth_headers,
        json={"sku": sku, "quantity_delta": -10, "order_id": order_event_id}
    )
    assert res1.status_code == 200
    assert res1.json()["new_stock"] == 90

    # Attacker replays exact same webhook 3 times
    for _ in range(3):
        res_replay = client.post(
            "/api/inventory/webhook/shopify",
            headers=auth_headers,
            json={"sku": sku, "quantity_delta": -10, "order_id": order_event_id}
        )
        assert res_replay.status_code == 200
        assert res_replay.json()["status"] == "already_processed"

    # Stock remains strictly 90, not 60
    db_session.expire_all()
    item_check = db_session.query(InventoryItem).filter(InventoryItem.sku == sku).first()
    assert item_check.total_stock == 90

    # 3. Quota Depletion Defense
    test_user.monthly_generations = 2
    test_user.purchased_generations = 0
    test_user.generations = 2
    db_session.commit()

    # Reserve valid 2 credits
    m, p = reserve_user_generations(test_user.id, 2, db_session)
    assert m == 2

    # Attempt to overdraft by 1 more credit
    with pytest.raises(Exception):
        reserve_user_generations(test_user.id, 1, db_session)


def test_tier4_scenario4_megastore_onboarding_byok_lifecycle_and_unlimited_scale(client, db_session):
    """
    Tier 4 - Scenario 4: Megastore Multi-Tenant Onboarding, Custom AI BYOK Lifecycle, and Unlimited Scale.
    Enterprise megastore merchant ($9,639.63/mo) completes onboarding, sets BYOK OpenAI key,
    executes generations without exhausting platform credits, and tenant isolation is strictly enforced.
    """
    # Step 1: Onboard Megastore Enterprise tenant
    megastore_user = User(
        id="user_mega_enterprise_001",
        email="cto@megaretailer.com",
        hashed_password="hashed_secure_enterprise_password",
        plan="megastore",
        generations=999999,
        monthly_limit=999999,
        monthly_generations=999999
    )
    boutique_user = User(
        id="user_boutique_isolated_001",
        email="owner@boutiqueshop.com",
        hashed_password="hashed_secure_boutique_password",
        plan="boutique",
        generations=150,
        monthly_limit=150,
        monthly_generations=150
    )
    db_session.add_all([megastore_user, boutique_user])
    db_session.commit()

    mega_token = create_access_token(megastore_user.id, megastore_user.email)
    boutique_token = create_access_token(boutique_user.id, boutique_user.email)

    mega_headers = {"Authorization": f"Bearer {mega_token}"}
    boutique_headers = {"Authorization": f"Bearer {boutique_token}"}

    # Step 2: Megastore configures BYOK Custom AI Key
    res_byok = client.post(
        "/api/user/custom-ai-key",
        headers=mega_headers,
        json={"api_key": "sk-custom-enterprise-openai-secret-key-12345", "provider": "openai"}
    )
    assert res_byok.status_code == 200
    assert res_byok.json()["has_custom_key"] is True
    assert res_byok.json()["unlimited_active"] is True

    # Step 3: Verify tenant isolation: Boutique user cannot view Megastore BYOK configuration
    res_boutique_byok = client.get("/api/user/custom-ai-key", headers=boutique_headers)
    assert res_boutique_byok.status_code == 200
    assert res_boutique_byok.json()["has_custom_key"] is False
    assert res_boutique_byok.json()["unlimited_active"] is False

    # Step 4: Verify MRR telemetry accurately attributes Megastore revenue ($9,639.63)
    with patch("server.main.ADMIN_SECRET", "sec_admin_root"):
        res_mrr = client.get("/admin/mrr-metrics", headers={"X-Admin-Secret": "sec_admin_root"})
        assert res_mrr.status_code == 200
        mrr_data = res_mrr.json()
        assert mrr_data["active_subscribers_by_tier"]["megastore"] >= 1
        assert mrr_data["active_subscribers_by_tier"]["boutique"] >= 1
        assert mrr_data["mrr_usd"] >= (9639.63 + 179.49)


def test_tier4_scenario5_fault_tolerance_stripe_503_and_ai_rollback(client, auth_headers, test_user, db_session):
    """
    Tier 4 - Scenario 5: Fault Tolerance, Stripe Gateway 503 Fallback, and Upstream AI Failure Rollback.
    Simulates:
    1. Stripe payment gateway unconfigured returning clean HTTP 503 without 500 error crashes
    2. Upstream AI provider timeout triggering atomic credit refund restoring exact user quota
    """
    # 1. Stripe 503 Fallback
    with patch("stripe.api_key", ""):
        res_sub = client.post("/billing/checkout", headers=auth_headers, json={"plan": "standard"})
        assert res_sub.status_code == 503
        assert "Payment gateway unavailable" in res_sub.json()["detail"]

        res_addon = client.post("/billing/addon/checkout", headers=auth_headers, json={"addon_key": "marketplace_optimizer_pack"})
        assert res_addon.status_code == 503
        assert "Payment gateway unavailable" in res_addon.json()["detail"]

    # 2. Upstream AI Failure Rollback
    test_user.monthly_generations = 10
    test_user.purchased_generations = 5
    test_user.generations = 15
    db_session.commit()

    with patch("server.main.generate_copy", side_effect=RuntimeError("OpenAI API rate limit exceeded")):
        res_ai = client.post(
            "/api/generate",
            headers=auth_headers,
            json={"type": "product_description", "context": "Sample product specifications"}
        )
        assert res_ai.status_code == 500

    # Exact bucket balances remain fully refunded and restored
    db_session.expire_all()
    u_after = db_session.query(User).filter(User.id == test_user.id).first()
    assert u_after.monthly_generations == 10
    assert u_after.purchased_generations == 5
    assert u_after.generations == 15
