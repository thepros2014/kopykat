from server.database import InventoryItem, InventorySyncLog, UserIntegration
from server.inventory import normalize_platform_name, reconcile_inventory_sku, sync_inventory_across_platforms

def test_inventory_item_crud(client, auth_headers, test_user, db_session):
    res = client.post("/api/inventory/item", json={"sku": "BACKPACK-001", "title": "UltraShield Backpack", "total_stock": 50}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["sku"] == "BACKPACK-001"
    assert data["total_stock"] == 50
    list_res = client.get("/api/inventory", headers=auth_headers)
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) >= 1
    assert any(i["sku"] == "BACKPACK-001" for i in items)

def test_inventory_webhook_and_fanout(client, auth_headers, test_user, db_session):
    db_session.query(UserIntegration).filter(UserIntegration.user_id == test_user.id).delete()
    db_session.add(UserIntegration(id="mock-sh-integ", user_id=test_user.id, platform="shopify", credentials="mock", status="connected"))
    db_session.add(UserIntegration(id="mock-ebay-integ", user_id=test_user.id, platform="ebay", credentials="mock", status="connected"))
    db_session.commit()
    client.post("/api/inventory/item", json={"sku": "SHIRT-RED-L", "title": "Red Linen Shirt", "total_stock": 20}, headers=auth_headers)
    res = client.post("/api/inventory/webhook/shopify", json={"sku": "SHIRT-RED-L", "quantity_delta": -2}, headers=auth_headers)
    assert res.status_code == 200
    result = res.json()
    assert result["sku"] == "SHIRT-RED-L"
    assert result["new_stock"] == 18
    assert result["previous_stock"] == 20
    assert result["fanout_results"]["shopify"] == "source_event"
    assert "synced_to_18" in result["fanout_results"]["ebay"]
    logs_res = client.get("/api/inventory/logs", headers=auth_headers)
    assert logs_res.status_code == 200
    logs = logs_res.json()
    assert len(logs) >= 1
    assert logs[0]["sku"] == "SHIRT-RED-L"
    assert logs[0]["quantity_change"] == -2

def test_inventory_fanout_all_eight_platforms(client, auth_headers, test_user, db_session):
    db_session.query(UserIntegration).filter(UserIntegration.user_id == test_user.id).delete()
    for p in ["shopify", "amazon", "etsy", "tiktok", "ebay", "walmart", "temu", "woocommerce"]:
        db_session.add(UserIntegration(id=f"mock-{p}-integ", user_id=test_user.id, platform=p, credentials="mock", status="connected"))
    db_session.commit()
    client.post("/api/inventory/item", json={"sku": "ALL-PLAT-SKU", "title": "Universal Item", "total_stock": 100}, headers=auth_headers)
    res = client.post("/api/inventory/webhook/shopify", json={"sku": "ALL-PLAT-SKU", "quantity_delta": -5}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["new_stock"] == 95
    assert data["fanout_results"]["shopify"] == "source_event"
    for target in ["amazon", "etsy", "tiktok", "ebay", "walmart", "temu", "woocommerce"]:
        assert data["fanout_results"][target] == "synced_to_95"

def test_inventory_platform_alias_normalization():
    assert normalize_platform_name("TIKTOK_SHOP") == "tiktok"
    assert normalize_platform_name("tiktokshop") == "tiktok"
    assert normalize_platform_name("woo") == "woocommerce"
    assert normalize_platform_name("SHOPIFY") == "shopify"

def test_inventory_webhook_idempotency_deduplication(client, auth_headers, test_user, db_session):
    db_session.query(UserIntegration).filter(UserIntegration.user_id == test_user.id).delete()
    db_session.add(UserIntegration(id="mock-ebay-idemp", user_id=test_user.id, platform="ebay", credentials="mock", status="connected"))
    db_session.commit()
    client.post("/api/inventory/item", json={"sku": "IDEMP-SKU", "title": "Idempotent Item", "total_stock": 50}, headers=auth_headers)
    res1 = client.post("/api/inventory/webhook/shopify", json={"sku": "IDEMP-SKU", "quantity_delta": -1, "order_id": "evt-unique-12345"}, headers=auth_headers)
    assert res1.status_code == 200
    assert res1.json()["new_stock"] == 49
    res2 = client.post("/api/inventory/webhook/shopify", json={"sku": "IDEMP-SKU", "quantity_delta": -1, "order_id": "evt-unique-12345"}, headers=auth_headers)
    assert res2.status_code == 200
    assert res2.json()["status"] == "already_processed"

def test_inventory_reconcile_drift_correction(client, auth_headers, test_user, db_session):
    db_session.query(UserIntegration).filter(UserIntegration.user_id == test_user.id).delete()
    for p in ["shopify", "amazon"]:
        db_session.add(UserIntegration(id=f"mock-rec-{p}", user_id=test_user.id, platform=p, credentials="mock", status="connected"))
    db_session.commit()
    result = reconcile_inventory_sku(user_id=test_user.id, sku="DRIFT-SKU", canonical_stock=75, db=db_session)
    assert result["reconciled_stock"] == 75
    assert result["fanout_results"]["shopify"] == "reconciled_to_75"
    assert result["fanout_results"]["amazon"] == "reconciled_to_75"


def test_inventory_routes_reject_unsupported_platform_and_negative_stock(client, auth_headers):
    invalid_platform = client.post(
        "/api/inventory/webhook/not-a-platform",
        json={"sku": "SKU-1", "quantity_delta": -1},
        headers=auth_headers,
    )
    assert invalid_platform.status_code == 400

    negative_stock = client.post(
        "/api/inventory/reconcile?sku=SKU-1&canonical_stock=-1",
        headers=auth_headers,
    )
    assert negative_stock.status_code == 422
