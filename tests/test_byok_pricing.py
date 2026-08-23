import pytest
from server.billing import PLANS
from server.database import User
from server.auth import decrypt_credentials

def test_plans_pricing_structure():
    assert PLANS["free"]["price_usd"] == 0
    assert PLANS["free"]["monthly_generations"] == 5
    assert PLANS["free"]["connectors_allowed"] == 1

    assert PLANS["boutique"]["price_usd"] == 179.49
    assert PLANS["boutique"]["monthly_generations"] == 150
    assert PLANS["boutique"]["connectors_allowed"] == 2

    assert PLANS["standard"]["price_usd"] == 379.49
    assert PLANS["standard"]["monthly_generations"] == 1000
    assert PLANS["standard"]["connectors_allowed"] == 10

    assert PLANS["megastore"]["price_usd"] == 9639.63
    assert PLANS["megastore"]["monthly_generations"] == 2500
    assert PLANS["megastore"]["byok_unlimited"] is True

def test_byok_custom_key_forbidden_for_free_tier(client, auth_headers, test_user):
    # Free tier user cannot set custom key
    test_user.plan = "free"
    res = client.post(
        "/api/user/custom-ai-key",
        json={"api_key": "sk-mock-private-key-1234567890", "provider": "openai"},
        headers=auth_headers
    )
    assert res.status_code == 403

def test_byok_custom_key_allowed_for_megastore(client, auth_headers, test_user, db_session):
    test_user.plan = "megastore"
    db_session.commit()

    res = client.post(
        "/api/user/custom-ai-key",
        json={"api_key": "sk-mock-private-key-1234567890", "provider": "openai"},
        headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["success"] is True

    # Invariant: Secret is encrypted at rest, never plaintext
    db_session.expire_all()
    user = db_session.query(User).filter(User.id == test_user.id).first()
    assert user.custom_ai_key_encrypted is not None
    assert user.custom_ai_key_encrypted != "sk-mock-private-key-1234567890"
    assert decrypt_credentials(user.custom_ai_key_encrypted) == "sk-mock-private-key-1234567890"

    # Status check
    status_res = client.get("/api/user/custom-ai-key", headers=auth_headers)
    assert status_res.status_code == 200
    assert status_res.json()["has_custom_key"] is True
    assert status_res.json()["unlimited_active"] is True
