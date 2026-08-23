import pytest
from unittest.mock import patch
import server.billing
from server.database import User, Subscription, RevenueRecord

def test_stripe_webhook_subscription_and_invoice(client, db_session, test_user):
    sub_event = {
        "id": "evt_test_sub_created_123",
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_test_12345",
                "customer": "cus_test_12345",
                "status": "active",
                "metadata": {"user_id": test_user.id, "plan": "standard"}
            }
        }
    }

    invoice_event = {
        "id": "evt_test_invoice_paid_123",
        "type": "invoice.payment_succeeded",
        "data": {
            "object": {
                "id": "in_test_invoice_123",
                "subscription": "sub_test_12345",
                "customer": "cus_test_12345",
                "amount_paid": 37949,
                "currency": "usd"
            }
        }
    }

    with patch.object(server.billing, "STRIPE_WEBHOOK_SECRET", "whsec_test"), \
         patch("stripe.Webhook.construct_event", side_effect=lambda payload, sig, sec: sub_event):
        
        res = client.post(
            "/billing/webhook",
            json=sub_event,
            headers={"Stripe-Signature": "t=1614000000,v1=test_sig"}
        )
        assert res.status_code == 200
        assert res.json()["status"] == "processed"

        # Verify User upgraded to Standard (1,000 generations)
        db_session.expire_all()
        user = db_session.query(User).filter(User.id == test_user.id).first()
        assert user.plan == "standard"
        assert user.generations == 1000

    with patch.object(server.billing, "STRIPE_WEBHOOK_SECRET", "whsec_test"), \
         patch("stripe.Webhook.construct_event", side_effect=lambda payload, sig, sec: invoice_event):
        
        inv_res = client.post(
            "/billing/webhook",
            json=invoice_event,
            headers={"Stripe-Signature": "t=1614000000,v1=test_sig"}
        )
        assert inv_res.status_code == 200

        # Verify revenue record recorded
        rev = db_session.query(RevenueRecord).filter(RevenueRecord.user_id == test_user.id).first()
        assert rev is not None
        assert rev.amount_cents == 37949

def test_stripe_webhook_idempotency(client, db_session, test_user):
    mock_event = {
        "id": "evt_test_idempotent_999",
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_test_idem",
                "customer": "cus_test_idem",
                "status": "active",
                "metadata": {"user_id": test_user.id, "plan": "boutique"}
            }
        }
    }

    with patch.object(server.billing, "STRIPE_WEBHOOK_SECRET", "whsec_test"), \
         patch("stripe.Webhook.construct_event", return_value=mock_event):
        
        res1 = client.post("/billing/webhook", json=mock_event, headers={"Stripe-Signature": "t=1614000000,v1=test_sig"})
        assert res1.status_code == 200
        assert res1.json()["status"] == "processed"

        # Duplicate event should be rejected idempotently
        res2 = client.post("/billing/webhook", json=mock_event, headers={"Stripe-Signature": "t=1614000000,v1=test_sig"})
        assert res2.status_code == 200
        assert res2.json()["status"] == "already_processed"
