import pytest
from server.database import InventoryItem, InventorySyncLog, UserIntegration

def test_inventory_item_crud(client, auth_headers, test_user, db_session):
    # 1. Create SKU
    res = client.post(
        "/api/inventory/item",
        json={"sku": "BACKPACK-001", "title": "UltraShield Backpack", "total_stock": 50},
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["sku"] == "BACKPACK-001"
    assert data["total_stock"] == 50

    # 2. List SKUs
    list_res = client.get("/api/inventory", headers=auth_headers)
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) >= 1
    assert any(i["sku"] == "BACKPACK-001" for i in items)

def test_inventory_webhook_and_fanout(client, auth_headers, test_user, db_session):
    # Setup mock active integrations (Shopify source + eBay/Amazon targets)
    db_session.query(UserIntegration).filter(UserIntegration.user_id == test_user.id).delete()
    
    sh_integ = UserIntegration(
        id="mock-sh-integ",
        user_id=test_user.id,
        platform="shopify",
        credentials="mock",
        status="connected"
    )
    ebay_integ = UserIntegration(
        id="mock-ebay-integ",
        user_id=test_user.id,
        platform="ebay",
        credentials="mock",
        status="connected"
    )
    db_session.add(sh_integ)
    db_session.add(ebay_integ)
    db_session.commit()

    # Initial stock setup
    client.post(
        "/api/inventory/item",
        json={"sku": "SHIRT-RED-L", "title": "Red Linen Shirt", "total_stock": 20},
        headers=auth_headers
    )

    # Webhook triggers order sale on Shopify (-2 units)
    res = client.post(
        "/api/inventory/webhook/shopify",
        json={"sku": "SHIRT-RED-L", "quantity_delta": -2},
        headers=auth_headers
    )
    assert res.status_code == 200
    result = res.json()
    assert result["sku"] == "SHIRT-RED-L"
    assert result["new_stock"] == 18
    assert result["previous_stock"] == 20

    # Invariant: Shopify is skipped from fanout (source_event) and eBay receives sync
    assert result["fanout_results"]["shopify"] == "source_event"
    assert "synced_to_18" in result["fanout_results"]["ebay"]

    # Verify log record created
    logs_res = client.get("/api/inventory/logs", headers=auth_headers)
    assert logs_res.status_code == 200
    logs = logs_res.json()
    assert len(logs) >= 1
    assert logs[0]["sku"] == "SHIRT-RED-L"
    assert logs[0]["quantity_change"] == -2
