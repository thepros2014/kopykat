import pytest
from server.pricing_monitor import compute_pricing_analysis
from server.database import PriceMarginItem

def test_compute_pricing_analysis_logic():
    # 1. Healthy target margin met
    res = compute_pricing_analysis(cogs=20.0, selling_price=50.0, target_margin=40.0)
    assert res["status"] == "healthy"
    assert res["profit_per_unit_usd"] == 30.0
    assert res["current_margin_pct"] == 60.0

    # 2. Critical thin margin (< 15%)
    crit_res = compute_pricing_analysis(cogs=45.0, selling_price=50.0, target_margin=40.0)
    assert crit_res["status"] == "critical"
    assert crit_res["current_margin_pct"] == 10.0
    assert "CRITICAL" in crit_res["recommendation"]

    # 3. Competitor price headroom opportunity
    opp_res = compute_pricing_analysis(cogs=20.0, selling_price=50.0, competitor_price=75.0, target_margin=40.0)
    assert "OPPORTUNITY" in opp_res["recommendation"]

def test_price_margin_item_crud(client, auth_headers, test_user, db_session):
    # 1. Create Price Margin Item
    res = client.post(
        "/api/pricing/item",
        json={
            "sku": "HEADPHONES-PRO",
            "product_name": "Noise Cancelling Headphones",
            "cogs_usd": 35.0,
            "selling_price_usd": 99.0,
            "competitor_price_usd": 129.0,
            "target_margin_pct": 50.0
        },
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["sku"] == "HEADPHONES-PRO"
    assert data["profit_per_unit_usd"] == 64.0
    assert data["status"] == "healthy"
    item_id = data["id"]

    # 2. List Items
    list_res = client.get("/api/pricing/items", headers=auth_headers)
    assert list_res.status_code == 200
    items = list_res.json()
    assert any(i["sku"] == "HEADPHONES-PRO" for i in items)

    # 3. Delete Item
    del_res = client.delete(f"/api/pricing/item/{item_id}", headers=auth_headers)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True
