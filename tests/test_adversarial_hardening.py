import pytest
import uuid
import json
from unittest.mock import patch
import server.billing
from server.database import User, APIKey, Subscription, CustomConnector, InventoryItem, BrandPersona, StripeEvent, UserEntitlement
from server.billing import handle_stripe_webhook, user_has_entitlement

def test_purchased_generations_preserved_on_subscription_renewal(client, db_session, test_user):
    # 1. User starts with 5 monthly generations, buys Starter Pack (+250 purchased)
    test_user.monthly_generations = 5
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
    assert user.monthly_generations == 150
    assert user.purchased_generations == 250
    assert user.generations == 400

def test_no_double_counting_of_consumed_purchased_credits_on_renewal(client, db_session, test_user):
    # User has exhausted monthly credits (0), and has 250 purchased credits
    test_user.monthly_generations = 0
    test_user.purchased_generations = 250
    test_user.generations = 250
    test_user.plan = "boutique"
    test_user.monthly_limit = 150

    sub = Subscription(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        stripe_subscription_id="sub_test_renewal_nodouble",
        plan="boutique",
        status="active"
    )
    db_session.add(sub)
    db_session.commit()

    # User consumes 100 purchased credits
    test_user.purchased_generations = 150
    test_user.generations = 150
    db_session.commit()

    # Monthly renewal arrives
    renewal_event = {
        "id": f"evt_renew_{uuid.uuid4().hex[:8]}",
        "type": "invoice.payment_succeeded",
        "data": {
            "object": {
                "id": f"in_{uuid.uuid4().hex[:8]}",
                "subscription": "sub_test_renewal_nodouble",
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

    # User gets new 150 monthly + remaining 150 purchased = 300 total (NOT 400, no double count!)
    db_session.expire_all()
    user = db_session.query(User).filter(User.id == test_user.id).first()
    assert user.monthly_generations == 150
    assert user.purchased_generations == 150
    assert user.generations == 300

def test_purchased_generations_preserved_on_subscription_cancellation(client, db_session, test_user):
    test_user.monthly_generations = 1000
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

    # User plan reverts to free (5/mo), but retains remaining 500 purchased generations = 505 total
    db_session.expire_all()
    user = db_session.query(User).filter(User.id == test_user.id).first()
    assert user.plan == "free"
    assert user.monthly_generations == 5
    assert user.purchased_generations == 500
    assert user.generations == 505

def test_addon_fulfillment_grants_user_entitlement(client, db_session, test_user):
    # Verify user does not have brand voice training entitlement
    assert user_has_entitlement(test_user, "brand_voice_training", db_session) is False

    addon_event = {
        "id": f"evt_addon_{uuid.uuid4().hex[:8]}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": f"cs_addon_{uuid.uuid4().hex[:8]}",
                "mode": "payment",
                "metadata": {
                    "user_id": test_user.id,
                    "type": "addon",
                    "addon_key": "brand_voice_training"
                },
                "amount_total": 4900,
                "currency": "usd"
            }
        }
    }

    with patch.object(server.billing, "STRIPE_WEBHOOK_SECRET", "whsec_test"), \
         patch("stripe.Webhook.construct_event", side_effect=lambda payload, sig, sec: addon_event):
        res = client.post("/billing/webhook", json=addon_event, headers={"Stripe-Signature": "t=123,v1=sig"})
        assert res.status_code == 200

    # User must now have active entitlement in database
    db_session.expire_all()
    assert user_has_entitlement(test_user, "brand_voice_training", db_session) is True

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
        res1 = client.post("/billing/webhook", json=payment_event, headers={"Stripe-Signature": "t=123,v1=sig"})
        assert res1.status_code == 200
        assert res1.json()["status"] == "processed"

        db_session.expire_all()
        user1 = db_session.query(User).filter(User.id == test_user.id).first()
        gens_after_first = user1.generations

        res2 = client.post("/billing/webhook", json=payment_event, headers={"Stripe-Signature": "t=123,v1=sig"})
        assert res2.status_code == 200
        assert res2.json()["status"] == "already_processed"

        db_session.expire_all()
        user2 = db_session.query(User).filter(User.id == test_user.id).first()
        assert user2.generations == gens_after_first

def test_idor_cross_tenant_isolation(client, db_session, test_user, auth_headers):
    user_b = User(
        id=str(uuid.uuid4()),
        email="attacker@example.com",
        hashed_password="hash",
        plan="free"
    )
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

    res_del_key = client.delete(f"/api/keys/{api_key_b.id}", headers=auth_headers)
    assert res_del_key.status_code == 404

    db_session.refresh(api_key_b)
    assert api_key_b.is_active is True
