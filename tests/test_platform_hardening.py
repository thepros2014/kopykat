import pytest
from unittest.mock import patch
from server.database import User, InventoryItem, InventorySyncLog
from server.content_governance import audit_generated_content
from server.inventory import reconcile_inventory_sku

def test_content_governance_defamation_filter():
    unsafe_text = "This competitor is a criminal fraud and scam that was sued."
    is_safe, flagged, cleaned = audit_generated_content(unsafe_text)
    assert is_safe is False
    assert len(flagged) >= 1
    assert "fraud" not in cleaned.lower()
    assert "scam" not in cleaned.lower()

def test_content_governance_unsubstantiated_claims():
    unsafe_text = "Our product is guaranteed to make you rich with a 100% cure."
    is_safe, flagged, cleaned = audit_generated_content(unsafe_text)
    assert is_safe is False
    assert len(flagged) >= 2
    assert "guaranteed to make you rich" not in cleaned.lower()

def test_inventory_reconcile_drift_correction(db_session, test_user):
    # Seed an inventory item with 50 stock
    item = InventoryItem(
        id="item_reconcile_001",
        user_id=test_user.id,
        sku="TEST-DRIFT-SKU",
        title="Drift Testing Product",
        total_stock=50,
        platform_stock='{"shopify": 50, "amazon": 45}'
    )
    db_session.add(item)
    db_session.commit()

    # Reconcile to canonical 42
    result = reconcile_inventory_sku(
        user_id=test_user.id,
        sku="TEST-DRIFT-SKU",
        canonical_stock=42,
        db=db_session
    )

    assert result["sku"] == "TEST-DRIFT-SKU"
    assert result["previous_stock"] == 50
    assert result["reconciled_stock"] == 42
    assert result["drift_corrected"] == -8

    # Verify DB item updated
    updated_item = db_session.query(InventoryItem).filter(InventoryItem.sku == "TEST-DRIFT-SKU").first()
    assert updated_item.total_stock == 42

    # Verify audit log recorded
    log = db_session.query(InventorySyncLog).filter(InventorySyncLog.sku == "TEST-DRIFT-SKU").first()
    assert log is not None
    assert log.trigger_platform == "reconciliation_engine"
    assert log.quantity_change == -8

def test_security_headers_and_csp(client):
    res = client.get("/health")
    assert res.status_code == 200
    headers = res.headers
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in headers
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert "X-XSS-Protection" not in headers  # Deprecated header eliminated

def test_generate_refund_on_ai_failure(client, auth_headers, db_session, test_user):
    initial_generations = test_user.generations
    
    # Mock generate_copy to raise an error
    with patch("server.main.generate_copy", side_effect=RuntimeError("AI Provider Timeout")):
        res = client.post("/api/generate", json={
            "type": "product_description",
            "context": "Ultra durable camping boots",
            "variations": 2
        }, headers=auth_headers)
        assert res.status_code == 500

    # User's generation balance must be fully refunded
    db_session.refresh(test_user)
    assert test_user.generations == initial_generations
