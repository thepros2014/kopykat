import pytest
from server.database import BrandPersona

def test_list_addons_catalog(client):
    res = client.get("/api/billing/addons")
    assert res.status_code == 200
    addons = res.json()
    assert len(addons) == 4
    keys = [a["key"] for a in addons]
    assert "brand_voice_training" in keys
    assert "marketplace_optimizer_pack" in keys
    assert "done_for_you_marketing_pack" in keys
    assert "bulk_catalog_import_pass" in keys

def test_brand_persona_crud(client, auth_headers):
    # Initially None
    res1 = client.get("/api/brand-persona", headers=auth_headers)
    assert res1.status_code == 200

    # Save persona
    payload = {
        "brand_name": "LuxeCraft Studio",
        "brand_voice_tone": "Refined, minimalistic, and poetic",
        "target_audience": "Design-conscious professionals",
        "rules_and_guidelines": "Avoid hype words. Emphasize craftsmanship.",
        "sample_copy": "Hand-forged from recycled titanium."
    }
    res2 = client.post("/api/brand-persona", json=payload, headers=auth_headers)
    assert res2.status_code == 200
    data = res2.json()
    assert data["brand_name"] == "LuxeCraft Studio"
    assert data["brand_voice_tone"] == "Refined, minimalistic, and poetic"

    # Verify retrieval
    res3 = client.get("/api/brand-persona", headers=auth_headers)
    assert res3.status_code == 200
    assert res3.json()["brand_name"] == "LuxeCraft Studio"

def test_marketplace_listing_optimizer_amazon(client, auth_headers):
    payload = {
        "product_name": "Titanium Thermal Flask",
        "platform": "amazon",
        "raw_details": "Double-wall insulated bottle, keeps hot 12h cold 24h, zero leak lid.",
        "keywords": "titanium water bottle, insulated flask, travel mug",
        "target_audience": "Hikers and everyday commuters"
    }
    res = client.post("/api/optimizer/marketplace-listing", json=payload, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["platform"] == "amazon"
    assert len(data["bullet_points"]) >= 4
    assert data["compliance_score"] >= 90
    assert data["backend_search_terms"] is not None

def test_marketplace_listing_optimizer_etsy(client, auth_headers):
    payload = {
        "product_name": "Handmade Ceramic Espresso Cup",
        "platform": "etsy",
        "raw_details": "Hand-thrown speckled stoneware clay with satin matte glaze. 3oz capacity.",
        "keywords": "handmade espresso cup, ceramic mug, pottery gift",
        "target_audience": "Coffee lovers"
    }
    res = client.post("/api/optimizer/marketplace-listing", json=payload, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["platform"] == "etsy"
    assert len(data["tags"]) >= 10
    assert data["compliance_score"] >= 90

def test_marketplace_listing_optimizer_shopify(client, auth_headers):
    payload = {
        "product_name": "Ergonomic Desk Mat",
        "platform": "shopify",
        "raw_details": "Vegan leather desk pad, waterproof, anti-slip suede base.",
        "keywords": "desk pad, ergonomic workspace",
        "target_audience": "Remote workers"
    }
    res = client.post("/api/optimizer/marketplace-listing", json=payload, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["platform"] == "shopify"
    assert data["meta_description"] is not None
    assert data["compliance_score"] >= 90

def test_addon_checkout_session(client, auth_headers):
    res = client.post(
        "/billing/addon/checkout",
        json={"addon_key": "marketplace_optimizer_pack"},
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert "checkout_url" in data
    assert "Marketplace Listing Optimizer Pack" in data["addon"]
