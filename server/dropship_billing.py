"""Private paid-placement activation flow for dropship directory partners.

The public directory is deliberately separate from this module. Partner
contact addresses are read from deployment-only environment variables, never
returned by an API, and never persisted in the database. A partner receives a
short-lived, single-use activation link; a signed Stripe webhook is the only
way to move a listing into the public ``active`` state.
"""

from __future__ import annotations

import hashlib
import html
import ipaddress
import logging
import os
import re
import secrets
from datetime import datetime, timedelta
from email.utils import parseaddr
from typing import Any, Optional
from urllib.parse import quote, urlsplit

import stripe
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import PUBLIC_BASE_URL
from .database import PartnerListing, PartnerPlacementReservation, RevenueRecord
from .dropship_connectors import PARTNERS

logger = logging.getLogger(__name__)

ACTIVATION_TOKEN_TTL = timedelta(days=14)
INVITE_RESEND_COOLDOWN = timedelta(days=30)
CHECKOUT_RESERVATION_TTL = timedelta(minutes=30)

# Price IDs and amounts belong in deployment configuration. The application
# never accepts a price ID or amount from a browser request. Featured slots
# are the five front-page positions. Directory slots are ranked 1-8, priced
# at $1,200, $1,100, ... $500 per year.
FEATURED_SLOT_COUNT = 5
DIRECTORY_SLOT_COUNT = 8
FEATURED_PLACEMENT_PLANS: dict[str, dict[str, Any]] = {
    "monthly": {
        "label": "Featured front page - 12 monthly payments totaling $3,200",
        "description": "Recurring monthly featured placement for one of five front-page slots.",
        "price_id_env": "STRIPE_PRICE_DROPSHIP_FEATURED_MONTHLY",
    },
    "yearly": {
        "label": "Featured front page - $2,200 per year",
        "description": "Recurring annual featured placement for one of five front-page slots.",
        "price_id_env": "STRIPE_PRICE_DROPSHIP_FEATURED_ANNUAL",
    },
}

_SAFE_EMAIL_RE = re.compile(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+")


def _utcnow() -> datetime:
    """Return a naive UTC timestamp matching the existing database models."""

    return datetime.utcnow()


def _valid_configured_email(value: str) -> str:
    """Accept only a plain address suitable for an SMTP header."""

    candidate = (value or "").strip()
    if not candidate or "\r" in candidate or "\n" in candidate:
        return ""
    _, address = parseaddr(candidate)
    if address != candidate or not _SAFE_EMAIL_RE.fullmatch(address):
        return ""
    return address


def partner_contact_email(partner_key: str) -> str:
    """Resolve a private partner contact address from deployment config."""

    partner = PARTNERS.get(partner_key)
    if not partner:
        return ""
    return _valid_configured_email(os.getenv(partner.get("contact_email_env", ""), ""))


def _activation_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_activation_token() -> str:
    return secrets.token_urlsafe(32)


def _get_or_create_listing(partner_key: str, db: Session) -> PartnerListing:
    if partner_key not in PARTNERS:
        raise HTTPException(status_code=404, detail="Unknown dropship partner.")
    listing = db.query(PartnerListing).filter(PartnerListing.partner_key == partner_key).first()
    if listing:
        if not listing.activation_id:
            listing.activation_id = secrets.token_hex(16)
        return listing
    listing = PartnerListing(
        partner_key=partner_key,
        status="pending",
        activation_id=secrets.token_hex(16),
    )
    db.add(listing)
    db.flush()
    return listing


def _listing_for_token(token: str, db: Session) -> PartnerListing:
    normalized = (token or "").strip()
    if len(normalized) < 32 or len(normalized) > 128:
        raise HTTPException(status_code=404, detail="Activation link is invalid or expired.")
    listing = db.query(PartnerListing).filter(
        PartnerListing.activation_token_hash == _activation_token_hash(normalized)
    ).first()
    if not listing or not listing.activation_token_expires_at:
        raise HTTPException(status_code=404, detail="Activation link is invalid or expired.")
    if listing.activation_token_expires_at < _utcnow():
        raise HTTPException(status_code=410, detail="Activation link has expired.")
    return listing


def _clear_activation_token(listing: PartnerListing) -> None:
    listing.activation_token_hash = None
    listing.activation_token_expires_at = None


def _activation_link(token: str) -> str:
    return f"{PUBLIC_BASE_URL}/dropship-partners/activate?token={quote(token, safe='')}"


def _validate_slot(placement_type: str, slot: int) -> int:
    if placement_type == "featured":
        max_slot = FEATURED_SLOT_COUNT
    elif placement_type == "directory":
        max_slot = DIRECTORY_SLOT_COUNT
    else:
        raise HTTPException(status_code=400, detail="Choose a featured or directory placement.")
    if slot < 1 or slot > max_slot:
        raise HTTPException(status_code=400, detail="That placement slot is not available.")
    return slot


def _placement_product(placement_type: str, slot: int, interval: str) -> dict[str, Any]:
    slot = _validate_slot(placement_type, slot)
    if interval not in {"monthly", "yearly"}:
        raise HTTPException(status_code=400, detail="Choose a monthly or yearly placement plan.")
    if placement_type == "featured":
        return {
            "placement_type": placement_type,
            "slot": slot,
            "interval": interval,
            **FEATURED_PLACEMENT_PLANS[interval],
        }
    if interval != "yearly":
        raise HTTPException(status_code=400, detail="Ranked dropshipping-tab placements are billed annually.")
    annual_amount = 1_200 - ((slot - 1) * 100)
    return {
        "placement_type": placement_type,
        "slot": slot,
        "interval": interval,
        "label": f"Dropshipping tab position {slot} - ${annual_amount:,} per year",
        "description": "Recurring annual paid placement in the ranked dropshipping tab.",
        "price_id_env": f"STRIPE_PRICE_DROPSHIP_DIRECTORY_SLOT_{slot}_ANNUAL",
    }


def _validate_public_https_url(value: Optional[str], fallback: Optional[str] = None) -> Optional[str]:
    """Validate partner-supplied public links without fetching or proxying them."""

    candidate = (value or "").strip()
    if not candidate:
        return fallback
    if len(candidate) > 2_000 or any(char in candidate for char in "\r\n\0"):
        raise HTTPException(status_code=400, detail="Partner links must be valid HTTPS URLs.")
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="Partner links must use HTTPS without embedded credentials.")
    try:
        address = ipaddress.ip_address(parsed.hostname)
        if not address.is_global:
            raise HTTPException(status_code=400, detail="Partner links cannot target private or reserved addresses.")
    except ValueError:
        pass
    return candidate


def _slot_in_use(
    placement_type: str,
    slot: int,
    listing: PartnerListing,
    db: Session,
) -> bool:
    listing_conflicts = db.query(PartnerListing).filter(
        PartnerListing.partner_key != listing.partner_key,
        PartnerListing.placement_type == placement_type,
        PartnerListing.placement_slot == slot,
        PartnerListing.status.in_(("active", "checkout_started")),
    ).all()
    now = _utcnow()
    for listing_conflict in listing_conflicts:
        if (
            listing_conflict.status == "checkout_started"
            and not listing_conflict.stripe_checkout_session_id
            and listing_conflict.updated_at
            and listing_conflict.updated_at <= now - CHECKOUT_RESERVATION_TTL
        ):
            continue
        return True

    reservations = db.query(PartnerPlacementReservation).filter(
        PartnerPlacementReservation.placement_type == placement_type,
        PartnerPlacementReservation.placement_slot == slot,
    ).all()
    for reservation in reservations:
        if reservation.partner_key == listing.partner_key and reservation.activation_id == listing.activation_id:
            continue
        if reservation.status == "checkout" and reservation.expires_at and reservation.expires_at <= now:
            db.delete(reservation)
            continue
        return True
    return False


def _reserve_slot(
    listing: PartnerListing,
    placement_type: str,
    slot: int,
    db: Session,
) -> PartnerPlacementReservation:
    """Reserve a slot before calling Stripe, closing the checkout race."""

    now = _utcnow()
    existing = db.query(PartnerPlacementReservation).filter(
        PartnerPlacementReservation.placement_type == placement_type,
        PartnerPlacementReservation.placement_slot == slot,
    ).first()
    if existing:
        same_activation = (
            existing.partner_key == listing.partner_key
            and existing.activation_id == listing.activation_id
        )
        if same_activation:
            if existing.status == "checkout" and existing.expires_at and existing.expires_at <= now:
                existing.expires_at = now + CHECKOUT_RESERVATION_TTL
                db.flush()
            return existing
        if existing.status == "checkout" and existing.expires_at and existing.expires_at <= now:
            db.delete(existing)
            db.flush()
        else:
            raise HTTPException(status_code=409, detail="That placement slot has just been taken.")

    reservation = PartnerPlacementReservation(
        placement_type=placement_type,
        placement_slot=slot,
        partner_key=listing.partner_key,
        activation_id=listing.activation_id or "",
        status="checkout",
        expires_at=now + CHECKOUT_RESERVATION_TTL,
    )
    db.add(reservation)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="That placement slot has just been taken.") from None
    return reservation


def _release_slot(listing: PartnerListing, db: Session) -> None:
    db.query(PartnerPlacementReservation).filter(
        PartnerPlacementReservation.partner_key == listing.partner_key,
        PartnerPlacementReservation.activation_id == listing.activation_id,
    ).delete(synchronize_session=False)


def _available_placement_options(listing: PartnerListing, db: Session) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for placement_type, slot_count in (
        ("featured", FEATURED_SLOT_COUNT),
        ("directory", DIRECTORY_SLOT_COUNT),
    ):
        for slot in range(1, slot_count + 1):
            if _slot_in_use(placement_type, slot, listing, db):
                continue
            intervals = ("monthly", "yearly") if placement_type == "featured" else ("yearly",)
            options.append({
                "placement_type": placement_type,
                "slot": slot,
                "plans": [
                    {
                        "interval": interval,
                        "label": _placement_product(placement_type, slot, interval)["label"],
                        "description": _placement_product(placement_type, slot, interval)["description"],
                    }
                    for interval in intervals
                ],
            })
    return options


def _send_email(subject: str, body: str, to: str) -> bool:
    """Lazy wrapper keeps the scheduler import one-directional and testable."""

    from .scheduler import _send_email as scheduler_send_email

    return bool(scheduler_send_email(subject, body, to))


def send_partner_activation_invite(partner_key: str, db: Session) -> dict[str, str]:
    """Send one partner-specific invite, respecting cooldown and paid state."""

    partner = PARTNERS.get(partner_key)
    if not partner:
        raise HTTPException(status_code=404, detail="Unknown dropship partner.")

    contact = partner_contact_email(partner_key)
    if not contact:
        return {"partner_key": partner_key, "status": "skipped", "reason": "contact_not_configured"}

    now = _utcnow()
    listing = _get_or_create_listing(partner_key, db)
    if listing.status == "active":
        db.commit()
        return {"partner_key": partner_key, "status": "skipped", "reason": "already_active"}
    if listing.invite_sent_at and now - listing.invite_sent_at < INVITE_RESEND_COOLDOWN:
        db.commit()
        return {"partner_key": partner_key, "status": "skipped", "reason": "cooldown"}

    old_activation_id = listing.activation_id
    token = _new_activation_token()
    listing.status = "pending"
    listing.activation_id = secrets.token_hex(16)
    listing.placement_type = "directory"
    listing.placement_slot = None
    listing.logo_url = None
    listing.service_url = None
    listing.billing_interval = None
    listing.stripe_customer_id = None
    listing.stripe_subscription_id = None
    listing.stripe_checkout_session_id = None
    listing.stripe_checkout_url = None
    db.query(PartnerPlacementReservation).filter(
        PartnerPlacementReservation.partner_key == listing.partner_key,
        PartnerPlacementReservation.activation_id == old_activation_id,
    ).delete(synchronize_session=False)
    listing.activation_token_hash = _activation_token_hash(token)
    listing.activation_token_expires_at = now + ACTIVATION_TOKEN_TTL
    db.commit()

    safe_name = html.escape(str(partner["name"]))
    safe_link = html.escape(_activation_link(token), quote=True)
    body = (
        "<html><body style='font-family:Arial,sans-serif;max-width:640px;margin:auto;padding:24px;'>"
        f"<h2>KopyKat partner placement invitation</h2>"
        f"<p>{safe_name} has been selected for a potential paid placement in KopyKat's "
        "dropship partner directory.</p>"
        "<p>This private activation link lets your team choose one of five featured front-page "
        "slots or one of the ranked dropshipping-tab positions through Stripe. Your listing "
        "will not be published until Stripe confirms payment.</p>"
        f"<p><a href='{safe_link}'>Review placement options</a></p>"
        "<p>This link expires in 14 days and is intended only for the company receiving this email.</p>"
        "</body></html>"
    )
    sent = _send_email(f"KopyKat paid placement invitation — {partner['name']}", body, contact)
    if sent:
        listing.invite_sent_at = now
        db.commit()
        return {"partner_key": partner_key, "status": "sent"}

    # Do not consume a failed delivery attempt. A later scheduler run can issue
    # a fresh token once SMTP is configured or the transient error is resolved.
    listing.activation_token_hash = None
    listing.activation_token_expires_at = None
    db.commit()
    return {"partner_key": partner_key, "status": "skipped", "reason": "email_not_sent"}


def send_configured_partner_invites(db: Session, partner_key: Optional[str] = None) -> list[dict[str, str]]:
    """Email each configured partner separately; safe to run from a scheduler."""

    keys = [partner_key] if partner_key else list(PARTNERS)
    results: list[dict[str, str]] = []
    for key in keys:
        try:
            results.append(send_partner_activation_invite(key, db))
        except HTTPException:
            raise
        except Exception:
            db.rollback()
            logger.exception("Partner activation invite failed for key=%s", key)
            results.append({"partner_key": key, "status": "error"})
    return results


def activation_status(token: str, db: Session) -> dict[str, Any]:
    listing = _listing_for_token(token, db)
    partner = PARTNERS[listing.partner_key]
    return {
        "partner_key": listing.partner_key,
        "partner_name": partner["name"],
        "status": listing.status,
        "placement_options": _available_placement_options(listing, db),
    }


def _price_id(product: dict[str, Any]) -> str:
    price_id = os.getenv(product["price_id_env"], "").strip()
    if not price_id or len(price_id) > 255 or any(char.isspace() for char in price_id):
        raise HTTPException(status_code=503, detail="Partner placement billing is not configured.")
    return price_id


def create_partner_checkout(
    token: str,
    placement_type: str,
    slot: int,
    interval: str,
    logo_url: Optional[str],
    service_url: Optional[str],
    db: Session,
) -> dict[str, str]:
    listing = _listing_for_token(token, db)
    if listing.status == "active":
        raise HTTPException(status_code=409, detail="This partner placement is already active.")
    product = _placement_product(placement_type, slot, interval)
    if _slot_in_use(placement_type, slot, listing, db):
        raise HTTPException(status_code=409, detail="That placement slot has just been taken.")
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Stripe is not configured.")

    price_id = _price_id(product)
    if (
        listing.status == "checkout_started"
        and listing.placement_type == placement_type
        and listing.placement_slot == slot
        and listing.billing_interval == interval
        and listing.stripe_checkout_session_id
        and listing.stripe_checkout_url
    ):
        return {
            "checkout_url": listing.stripe_checkout_url,
            "session_id": listing.stripe_checkout_session_id,
        }

    partner = PARTNERS[listing.partner_key]
    if not listing.activation_id:
        listing.activation_id = secrets.token_hex(16)
    safe_logo_url = _validate_public_https_url(logo_url)
    safe_service_url = _validate_public_https_url(service_url, fallback=partner["docs_url"])
    reservation = _reserve_slot(listing, placement_type, slot, db)
    listing.status = "checkout_started"
    listing.placement_type = placement_type
    listing.placement_slot = slot
    listing.logo_url = safe_logo_url
    listing.service_url = safe_service_url
    listing.billing_interval = interval
    listing.stripe_checkout_session_id = None
    listing.stripe_checkout_url = None
    db.commit()

    encoded_token = quote(token.strip(), safe="")
    metadata = {
        "partner_key": listing.partner_key,
        "activation_id": listing.activation_id,
        "placement_type": placement_type,
        "placement_slot": str(slot),
        "billing_interval": interval,
    }
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=(
                f"{PUBLIC_BASE_URL}/dropship-partners/activate?token={encoded_token}&payment=success"
            ),
            cancel_url=(
                f"{PUBLIC_BASE_URL}/dropship-partners/activate?token={encoded_token}&payment=cancelled"
            ),
            metadata=metadata,
            subscription_data={"metadata": metadata},
            client_reference_id=f"partner:{listing.partner_key}",
            allow_promotion_codes=True,
            idempotency_key=f"partner-placement:{listing.partner_key}:{placement_type}:{slot}:{interval}",
        )
    except Exception:
        logger.exception("Partner Stripe checkout creation failed for key=%s", listing.partner_key)
        _release_slot(listing, db)
        listing.status = "pending"
        listing.placement_type = "directory"
        listing.placement_slot = None
        listing.logo_url = None
        listing.service_url = None
        listing.billing_interval = None
        listing.stripe_checkout_session_id = None
        listing.stripe_checkout_url = None
        db.commit()
        raise HTTPException(status_code=503, detail="Payment gateway error. Please try again later.") from None

    session_url = getattr(session, "url", None)
    session_id = getattr(session, "id", None)
    if not session_url or not session_id:
        _release_slot(listing, db)
        listing.status = "pending"
        listing.placement_type = "directory"
        listing.placement_slot = None
        listing.logo_url = None
        listing.service_url = None
        listing.billing_interval = None
        listing.stripe_checkout_session_id = None
        listing.stripe_checkout_url = None
        db.commit()
        raise HTTPException(status_code=503, detail="Payment gateway returned an incomplete checkout session.")

    reservation.stripe_checkout_session_id = str(session_id)
    listing.stripe_checkout_session_id = str(session_id)
    listing.stripe_checkout_url = str(session_url)
    db.commit()
    logger.info("Partner placement checkout created for key=%s interval=%s", listing.partner_key, interval)
    return {"checkout_url": str(session_url), "session_id": str(session_id)}


def _stripe_datetime(timestamp: object) -> Optional[datetime]:
    try:
        return datetime.utcfromtimestamp(float(timestamp)) if timestamp else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _metadata_partner_key(payload: dict[str, Any]) -> Optional[str]:
    metadata = payload.get("metadata") or {}
    key = metadata.get("partner_key")
    return key if key in PARTNERS else None


def _metadata_placement(payload: dict[str, Any]) -> Optional[tuple[str, int, str]]:
    metadata = payload.get("metadata") or {}
    placement_type = metadata.get("placement_type")
    interval = metadata.get("billing_interval")
    try:
        slot = int(metadata.get("placement_slot"))
        _placement_product(placement_type, slot, interval)
    except (TypeError, ValueError, HTTPException):
        return None
    return placement_type, slot, interval


def _apply_event_placement(listing: PartnerListing, payload: dict[str, Any]) -> None:
    placement = _metadata_placement(payload)
    if placement:
        listing.placement_type, listing.placement_slot, listing.billing_interval = placement


def _activate_listing(listing: PartnerListing, db: Session) -> None:
    if listing.placement_slot is None or _slot_in_use(
        listing.placement_type, listing.placement_slot, listing, db
    ):
        listing.status = "review_required"
        _release_slot(listing, db)
        logger.error("Partner placement slot unavailable during activation for key=%s", listing.partner_key)
        return
    listing.status = "active"
    reservation = db.query(PartnerPlacementReservation).filter(
        PartnerPlacementReservation.partner_key == listing.partner_key,
        PartnerPlacementReservation.activation_id == listing.activation_id,
        PartnerPlacementReservation.placement_type == listing.placement_type,
        PartnerPlacementReservation.placement_slot == listing.placement_slot,
    ).first()
    if reservation:
        reservation.status = "active"
        reservation.expires_at = None
    _clear_activation_token(listing)


def _listing_for_event(payload: dict[str, Any], db: Session) -> Optional[PartnerListing]:
    activation_id = (payload.get("metadata") or {}).get("activation_id")
    partner_key = _metadata_partner_key(payload)
    if activation_id and activation_id != partner_key:
        listing = db.query(PartnerListing).filter(
            PartnerListing.activation_id == activation_id
        ).first()
        if listing:
            return listing
        # A signed event for an older activation must never fall through to a
        # newer checkout for the same partner.
        return None

    subscription_id = payload.get("id") if payload.get("object") == "subscription" else payload.get("subscription")
    if subscription_id:
        listing = db.query(PartnerListing).filter(
            PartnerListing.stripe_subscription_id == subscription_id
        ).first()
        if listing:
            return listing
    if not partner_key:
        return None
    return db.query(PartnerListing).filter(PartnerListing.partner_key == partner_key).first()


def is_partner_event(payload: dict[str, Any]) -> bool:
    return _metadata_partner_key(payload) is not None


def handle_partner_checkout_completed(session: dict[str, Any], db: Session) -> bool:
    if not is_partner_event(session):
        return False
    listing = _listing_for_event(session, db)
    if not listing:
        logger.error("Stripe partner checkout refers to a missing listing")
        return True
    if session.get("subscription"):
        listing.stripe_subscription_id = str(session["subscription"])
    if session.get("customer"):
        listing.stripe_customer_id = str(session["customer"])
    _apply_event_placement(listing, session)
    if session.get("payment_status") in {"paid", "no_payment_required"}:
        _activate_listing(listing, db)
    return True


def handle_partner_subscription_created(subscription: dict[str, Any], db: Session) -> bool:
    if not is_partner_event(subscription):
        return False
    listing = _listing_for_event(subscription, db)
    if not listing:
        logger.error("Stripe partner subscription refers to a missing listing")
        return True
    listing.stripe_subscription_id = str(subscription.get("id")) if subscription.get("id") else listing.stripe_subscription_id
    listing.stripe_customer_id = str(subscription.get("customer")) if subscription.get("customer") else listing.stripe_customer_id
    _apply_event_placement(listing, subscription)
    listing.current_period_end = _stripe_datetime(subscription.get("current_period_end"))
    status = subscription.get("status", "active")
    if status in {"active", "trialing"}:
        _activate_listing(listing, db)
    elif status in {"past_due", "unpaid", "canceled", "incomplete_expired"}:
        listing.status = "past_due" if status == "past_due" else "canceled"
        if listing.status == "canceled":
            _release_slot(listing, db)
    else:
        listing.status = "checkout_started"
    return True


def handle_partner_invoice_paid(invoice: dict[str, Any], db: Session) -> bool:
    listing = _listing_for_event(invoice, db)
    if not listing:
        return False
    if listing.status not in {"canceled", "review_required"}:
        _activate_listing(listing, db)
    elif listing.status == "review_required":
        _release_slot(listing, db)
    payment_id = invoice.get("id")
    if payment_id and not db.query(RevenueRecord).filter(
        RevenueRecord.stripe_payment_id == payment_id
    ).first():
        db.add(RevenueRecord(
            id=secrets.token_hex(16),
            stripe_payment_id=str(payment_id),
            user_id=None,
            amount_cents=int(invoice.get("amount_paid") or 0),
            currency=str(invoice.get("currency") or "usd")[:3],
            # RevenueRecord.plan is intentionally short for compatibility with
            # existing deployments; the listing key remains in the payment
            # metadata and the typed record identifies this revenue class.
            plan="partner_listing",
            type="partner_listing",
            status="succeeded",
        ))
    _clear_activation_token(listing)
    return True


def handle_partner_subscription_changed(subscription: dict[str, Any], db: Session) -> bool:
    listing = _listing_for_event(subscription, db)
    if not listing:
        return False
    status = subscription.get("status", "")
    listing.current_period_end = _stripe_datetime(subscription.get("current_period_end")) or listing.current_period_end
    if status in {"active", "trialing"}:
        _activate_listing(listing, db)
    elif status == "past_due":
        listing.status = "past_due"
    elif status in {"canceled", "unpaid", "incomplete_expired"}:
        listing.status = "canceled"
        _release_slot(listing, db)
    else:
        listing.status = "checkout_started"
    return True


def handle_partner_payment_failed(invoice: dict[str, Any], db: Session) -> bool:
    listing = _listing_for_event(invoice, db)
    if not listing:
        return False
    listing.status = "past_due"
    return True


def active_partner_keys(db: Session) -> set[str]:
    rows = db.query(PartnerListing.partner_key).filter(PartnerListing.status == "active").all()
    return {row[0] for row in rows}


def active_partner_records(
    db: Session,
    placement_type: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Build the public directory projection from active paid listings only."""

    query = db.query(PartnerListing).filter(PartnerListing.status == "active")
    if placement_type:
        query = query.filter(PartnerListing.placement_type == placement_type)
    listings = query.all()
    listings.sort(key=lambda item: (item.placement_type != "featured", item.placement_slot or 999, item.partner_key))
    records: list[dict[str, Any]] = []
    for listing in listings:
        partner = PARTNERS.get(listing.partner_key)
        if not partner or not partner.get("paid_placement"):
            continue
        records.append({
            "key": partner["key"],
            "name": partner["name"],
            "niche": partner["niche"],
            "description": partner["description"],
            "docs_url": partner["docs_url"],
            "auth_type": partner["auth_type"],
            "regions": partner["regions"],
            "paid_placement": True,
            "placement_type": listing.placement_type,
            "placement_slot": listing.placement_slot,
            "logo_url": listing.logo_url,
            "service_url": listing.service_url or partner["docs_url"],
        })
    return records
