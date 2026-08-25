import re
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import server.billing
import stripe

from server.database import CustomConnector, PartnerListing, PartnerPlacementReservation, RevenueRecord
from server.dropship_billing import send_partner_activation_invite


def _token_from_invite(mock_send):
    body = mock_send.call_args.args[1]
    link = re.search(r"href='([^']+)'", body).group(1)
    return parse_qs(urlparse(link).query)["token"][0]


def test_public_directory_only_returns_active_paid_placements(client, db_session):
    db_session.add(PartnerListing(partner_key="printful", status="active"))
    db_session.add(PartnerListing(partner_key="printify", status="pending"))
    db_session.commit()

    response = client.get("/api/dropship-partners")

    assert response.status_code == 200
    payload = response.json()
    assert [partner["key"] for partner in payload["partners"]] == ["printful"]
    assert "contact_email" not in response.text
    assert "DROPSHIP_PARTNER_" not in response.text


def test_partner_invite_stores_only_a_hash_and_exposes_private_status(client, db_session, monkeypatch):
    monkeypatch.setenv("DROPSHIP_PARTNER_PRINTFUL_EMAIL", "partnerships@example.com")
    with patch("server.dropship_billing._send_email", return_value=True) as mock_send:
        result = send_partner_activation_invite("printful", db_session)

    assert result == {"partner_key": "printful", "status": "sent"}
    token = _token_from_invite(mock_send)
    listing = db_session.query(PartnerListing).filter_by(partner_key="printful").one()
    assert listing.activation_token_hash
    assert token not in listing.activation_token_hash
    assert listing.invite_sent_at is not None

    response = client.get("/api/dropship-partners/activation", params={"token": token})
    assert response.status_code == 200
    assert response.json()["partner_name"] == "Printful"
    assert len(response.json()["placement_options"]) == 13
    options = response.json()["placement_options"]
    assert "$2,200 per year" in options[0]["plans"][1]["label"]
    assert "$3,200" in options[0]["plans"][0]["label"]
    assert "$1,200 per year" in options[5]["plans"][0]["label"]
    assert "$500 per year" in options[-1]["plans"][0]["label"]
    assert "partnerships@example.com" not in response.text


def test_partner_checkout_uses_server_configured_stripe_price_and_is_idempotent(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("DROPSHIP_PARTNER_PRINTIFY_EMAIL", "partnerships@example.com")
    with patch("server.dropship_billing._send_email", return_value=True) as mock_send:
        send_partner_activation_invite("printify", db_session)
    token = _token_from_invite(mock_send)

    monkeypatch.setenv("STRIPE_PRICE_DROPSHIP_DIRECTORY_SLOT_3_ANNUAL", "price_partner_directory_3_test")
    monkeypatch.setattr(stripe, "api_key", "sk_test_partner")
    session = type(
        "Session",
        (),
        {"url": "https://checkout.stripe.com/c/pay/cs_partner_yearly", "id": "cs_partner_yearly"},
    )()
    with patch.object(stripe.checkout.Session, "create", return_value=session) as mock_create:
        response = client.post(
            "/api/dropship-partners/activation/checkout",
            json={
                "token": token,
                "placement_type": "directory",
                "slot": 3,
                "interval": "yearly",
                "logo_url": "https://printify.example/logo.png",
                "service_url": "https://printify.example/",
            },
        )
        repeated = client.post(
            "/api/dropship-partners/activation/checkout",
            json={
                "token": token,
                "placement_type": "directory",
                "slot": 3,
                "interval": "yearly",
                "logo_url": "https://printify.example/logo.png",
                "service_url": "https://printify.example/",
            },
        )

    assert response.status_code == 200
    assert repeated.status_code == 200
    assert response.json() == repeated.json()
    assert mock_create.call_count == 1
    kwargs = mock_create.call_args.kwargs
    assert kwargs["mode"] == "subscription"
    assert kwargs["line_items"] == [{"price": "price_partner_directory_3_test", "quantity": 1}]
    assert kwargs["metadata"]["partner_key"] == "printify"
    assert kwargs["metadata"]["placement_type"] == "directory"
    assert kwargs["metadata"]["placement_slot"] == "3"
    assert kwargs["metadata"]["billing_interval"] == "yearly"
    assert "partnerships@example.com" not in str(kwargs)

    reservation = db_session.query(PartnerPlacementReservation).filter_by(
        placement_type="directory", placement_slot=3
    ).one()
    assert reservation.partner_key == "printify"

    monkeypatch.setenv("DROPSHIP_PARTNER_CJ_EMAIL", "partnerships@example.com")
    with patch("server.dropship_billing._send_email", return_value=True) as second_send:
        send_partner_activation_invite("cjdropshipping", db_session)
    second_token = _token_from_invite(second_send)
    blocked = client.post(
        "/api/dropship-partners/activation/checkout",
        json={
            "token": second_token,
            "placement_type": "directory",
            "slot": 3,
            "interval": "yearly",
        },
    )
    assert blocked.status_code == 409


def test_public_directory_never_exposes_private_price_schedule(client, db_session):
    db_session.add(
        PartnerListing(
            partner_key="spocket",
            status="active",
            placement_type="featured",
            placement_slot=1,
            logo_url="https://spocket.example/logo.png",
            service_url="https://spocket.example/",
        )
    )
    db_session.commit()

    response = client.get("/api/dropship-partners")
    page = client.get("/dropship-partners")

    assert response.status_code == 200
    assert response.json()["partners"][0]["logo_url"] == "https://spocket.example/logo.png"
    assert response.json()["partners"][0]["service_url"] == "https://spocket.example/"
    assert "$2,200" not in response.text
    assert "$1,200" not in response.text
    assert "$2,200" not in page.text
    assert "$1,200" not in page.text


def test_partner_connector_requires_active_listing_and_sets_required_fields(
    client, db_session, auth_headers
):
    blocked = client.post("/api/dropship-partners/printful/connect", headers=auth_headers)
    assert blocked.status_code == 403

    db_session.add(PartnerListing(partner_key="printful", status="active"))
    db_session.commit()
    created = client.post("/api/dropship-partners/printful/connect", headers=auth_headers)

    assert created.status_code == 200
    connector = db_session.query(CustomConnector).filter_by(platform_name="Printful").one()
    assert connector.source_url == "https://developers.printful.com/docs/"
    assert connector.operation_count == 6
    assert connector.authentication_modes == "bearer"

    existing = client.post("/api/dropship-partners/printful/connect", headers=auth_headers)
    assert existing.status_code == 200
    assert existing.json()["status"] == "existing"


def test_partner_stripe_webhooks_activate_revenue_and_deactivate_listing(
    client, db_session, monkeypatch
):
    db_session.add(
        PartnerListing(
            partner_key="bigbuy",
            status="checkout_started",
            placement_type="directory",
            placement_slot=2,
            billing_interval="yearly",
            activation_token_hash="a" * 64,
        )
    )
    db_session.commit()
    monkeypatch.setattr(server.billing, "STRIPE_WEBHOOK_SECRET", "whsec_partner_test")

    subscription_event = {
        "id": "evt_partner_subscription_created",
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "object": "subscription",
                "id": "sub_partner_bigbuy",
                "customer": "cus_partner_bigbuy",
                "status": "active",
                "current_period_end": 1_900_000_000,
                "metadata": {
                    "partner_key": "bigbuy",
                    "activation_id": "bigbuy",
                    "placement_type": "directory",
                    "placement_slot": "2",
                    "billing_interval": "yearly",
                },
            }
        },
    }
    with patch("stripe.Webhook.construct_event", return_value=subscription_event):
        created = client.post(
            "/billing/webhook",
            json=subscription_event,
            headers={"Stripe-Signature": "t=1,v1=partner"},
        )
    assert created.status_code == 200
    listing = db_session.query(PartnerListing).filter_by(partner_key="bigbuy").one()
    assert listing.status == "active"
    assert listing.activation_token_hash is None

    invoice_event = {
        "id": "evt_partner_invoice_paid",
        "type": "invoice.payment_succeeded",
        "data": {
            "object": {
                "object": "invoice",
                "id": "in_partner_bigbuy",
                "subscription": "sub_partner_bigbuy",
                "amount_paid": 9900,
                "currency": "usd",
            }
        },
    }
    with patch("stripe.Webhook.construct_event", return_value=invoice_event):
        paid = client.post(
            "/billing/webhook",
            json=invoice_event,
            headers={"Stripe-Signature": "t=2,v1=partner"},
        )
    assert paid.status_code == 200
    revenue = db_session.query(RevenueRecord).filter_by(stripe_payment_id="in_partner_bigbuy").one()
    assert revenue.type == "partner_listing"
    assert revenue.user_id is None

    deleted_event = {
        "id": "evt_partner_subscription_deleted",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "object": "subscription",
                "id": "sub_partner_bigbuy",
                "status": "canceled",
            }
        },
    }
    with patch("stripe.Webhook.construct_event", return_value=deleted_event):
        deleted = client.post(
            "/billing/webhook",
            json=deleted_event,
            headers={"Stripe-Signature": "t=3,v1=partner"},
        )
    assert deleted.status_code == 200
    db_session.expire_all()
    assert db_session.query(PartnerListing).filter_by(partner_key="bigbuy").one().status == "canceled"
    assert client.get("/api/dropship-partners").json()["partners"] == []
