import pytest
import uuid
import json
from unittest.mock import patch
import server.billing
from server.database import User, APIKey, Subscription, CustomConnector, InventoryItem, BrandPersona, StripeEvent

def test_purchased_generations_preserved_on_subscription_renewal(client, db_session, test_user):
    # 1. User starts with 5 generations, buys Starter Pack (+250)
    test_user.purchased_generations = 250
    test_user.generations = 5 + 250
    test_user.plan = "boutique"
    test_user.monthly_limit = 150

    sub = Subscription(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        stripe_subscription_id="sub_test_renewal_123",
        plan="boutique",
        status="active"
    )
    db_session.add(sub)
    db_session.commit()

    # 2. Simulate invoice.payment_succeeded webhook for subscription renewal
    renewal_event = {
        "id": f"evt_renew_{uuid.uuid4().hex[:8]}",
        "type": "invoice.payment_succeeded",
        "data": {
            "object": {
                "id": f"in_{uuid.uuid4().hex[:8]}",
                "subscription": "sub_test_renewal_123",
                "customer": "cus_test_123",
                "amount_paid": 17949,
                "currency": "usd"
            }
        }
    }

    with patch.object(server.billing, "STRIPE_WEBHOOK_SECRET", "whsec_test"), \
         patch("stripe.Webhook.construct_event", side_effect=lambda payload, sig, sec: renewal_event):
        res = client.post("/billing/webhook", json=renewal_event, headers={"Stripe-Signature": "t=123,v1=sig"})
        assert res.status_code == 200
        assert res.json()["status"] == "processed"

    # 3. User must have Boutique monthly quota (150) + 250 purchased generations = 400 total
    db_session.expire_all()
    user = db_session.query(User).filter(User.id == test_user.id).first()
    assert user.purchased_generations == 250
    assert user.generations == 150 + 250

def test_purchased_generations_preserved_on_subscription_cancellation(client, db_session, test_user):
    test_user.purchased_generations = 500
    test_user.generations = 1000 + 500
    test_user.plan = "standard"

    sub = Subscription(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        stripe_subscription_id="sub_test_cancel_456",
        plan="standard",
        status="active"
    )
    db_session.add(sub)
    db_session.commit()

    # Simulate customer.subscription.deleted
    cancel_event = {
        "id": f"evt_cancel_{uuid.uuid4().hex[:8]}",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_test_cancel_456",
                "customer": "cus_test_123",
                "status": "canceled"
            }
        }
    }

    with patch.object(server.billing, "STRIPE_WEBHOOK_SECRET", "whsec_test"), \
         patch("stripe.Webhook.construct_event", side_effect=lambda payload, sig, sec: cancel_event):
        res = client.post("/billing/webhook", json=cancel_event, headers={"Stripe-Signature": "t=123,v1=sig"})
        assert res.status_code == 200
        assert res.json()["status"] == "processed"

    # User plan reverts to free, monthly quota to 5, but retains 500 purchased generations = 505 total
    db_session.expire_all()
    user = db_session.query(User).filter(User.id == test_user.id).first()
    assert user.plan == "free"
    assert user.purchased_generations == 500
    assert user.generations == 5 + 500

def test_webhook_replay_protection(client, db_session, test_user):
    event_id = f"evt_replay_{uuid.uuid4().hex[:8]}"
    payment_event = {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": f"cs_{uuid.uuid4().hex[:8]}",
                "mode": "payment",
                "metadata": {
                    "user_id": test_user.id,
                    "pack": "starter"
                },
                "amount_total": 500,
                "currency": "usd"
            }
        }
    }

    with patch.object(server.billing, "STRIPE_WEBHOOK_SECRET", "whsec_test"), \
         patch("stripe.Webhook.construct_event", side_effect=lambda payload, sig, sec: payment_event):
        # First event delivery
        res1 = client.post("/billing/webhook", json=payment_event, headers={"Stripe-Signature": "t=123,v1=sig"})
        assert res1.status_code == 200
        assert res1.json()["status"] == "processed"

        db_session.expire_all()
        user1 = db_session.query(User).filter(User.id == test_user.id).first()
        gens_after_first = user1.generations

        # Second event delivery (simulated duplicate replay)
        res2 = client.post("/billing/webhook", json=payment_event, headers={"Stripe-Signature": "t=123,v1=sig"})
        assert res2.status_code == 200
        assert res2.json()["status"] == "already_processed"

        db_session.expire_all()
        user2 = db_session.query(User).filter(User.id == test_user.id).first()
        assert user2.generations == gens_after_first  # Not double credited

def test_idor_cross_tenant_isolation(client, db_session, test_user, auth_headers):
    # Create another user B
    user_b = User(
        id=str(uuid.uuid4()),
        email="attacker@example.com",
        hashed_password="hash",
        plan="free"
    )
    # User B creates an inventory item and API key
    item_b = InventoryItem(
        id="item_user_b_secret",
        user_id=user_b.id,
        sku="SKU-USER-B",
        title="User B Product",
        total_stock=100
    )
    api_key_b = APIKey(
        id="key_user_b_secret",
        user_id=user_b.id,
        key_hash="hash_b_123",
        key_prefix="kk_b_123",
        name="User B Key"
    )
    db_session.add(user_b)
    db_session.add(item_b)
    db_session.add(api_key_b)
    db_session.commit()

    # Test user (User A) attempts to delete User B's API key
    res_del_key = client.delete(f"/api/keys/{api_key_b.id}", headers=auth_headers)
    assert res_del_key.status_code == 404  # Not found for User A

    # Verify User B's key is still active
    db_session.refresh(api_key_b)
    assert api_key_b.is_active is True
