"""
billing.py — Stripe integration for subscriptions, credit packs, and webhooks.
All money collection is automated. Stripe deposits earnings to your CashApp
account automatically on a schedule you set in the Stripe dashboard.
"""

import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

import stripe
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .database import User, Subscription, RevenueRecord, StripeEvent

logger = logging.getLogger(__name__)

# ── Stripe config ─────────────────────────────────────────────────────────────

stripe.api_key          = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET   = os.getenv("STRIPE_WEBHOOK_SECRET", "")
APP_BASE_URL            = os.getenv("APP_BASE_URL", "http://localhost:8000")

# ── Plan definitions ──────────────────────────────────────────────────────────
# Price IDs come from your Stripe dashboard — create these products once,
# then paste the price IDs into your .env file.

PLANS = {
    "basic": {
        "name":          "Basic",
        "price_id_env":  "STRIPE_PRICE_BASIC",        # $9/month
        "monthly_tokens": 50_000,
        "price_usd":     9,
        "features":      ["50,000 credits/mo (~500 generations)", "All 10 copy types", "1 API key", "Email support"],
    },
    "pro": {
        "name":          "Pro",
        "price_id_env":  "STRIPE_PRICE_PRO",           # $29/month
        "monthly_tokens": 250_000,
        "price_usd":     29,
        "features":      ["250,000 credits/mo (~2,500 generations)", "All 10 copy types", "3 API keys", "Priority support"],
    },
    "business": {
        "name":          "Business",
        "price_id_env":  "STRIPE_PRICE_BUSINESS",      # $79/month
        "monthly_tokens": 1_000_000,
        "price_usd":     79,
        "features":      ["1,000,000 credits/mo (~10,000 generations)", "All 10 copy types", "5 API keys", "Priority support", "Custom prompts"],
    },
}

# One-time credit packs (no subscription required)
CREDIT_PACKS = {
    "starter": {
        "name":         "Starter Pack (25,000 credits / ~250 gens)",
        "price_id_env": "STRIPE_PRICE_PACK_STARTER",  # $5 one-time
        "tokens":       25_000,
        "price_usd":    5,
    },
    "growth": {
        "name":         "Growth Pack (100,000 credits / ~1,000 gens)",
        "price_id_env": "STRIPE_PRICE_PACK_GROWTH",   # $15 one-time
        "tokens":       100_000,
        "price_usd":    15,
    },
    "scale": {
        "name":         "Scale Pack (300,000 credits / ~3,000 gens)",
        "price_id_env": "STRIPE_PRICE_PACK_SCALE",    # $40 one-time
        "tokens":       300_000,
        "price_usd":    40,
    },
}



def _get_price_id(env_var: str) -> str:
    price_id = os.getenv(env_var, "")
    if not price_id:
        raise HTTPException(
            status_code=503,
            detail=f"Billing not configured. Set {env_var} in environment variables."
        )
    return price_id


# ── Stripe customer management ────────────────────────────────────────────────

def get_or_create_stripe_customer(user: User, db: Session) -> str:
    """Returns the Stripe customer ID, creating one if it doesn't exist."""
    if user.stripe_customer_id:
        return user.stripe_customer_id

    customer = stripe.Customer.create(
        email=user.email,
        name=user.full_name or "",
        metadata={"user_id": user.id},
    )
    user.stripe_customer_id = customer.id
    db.commit()
    return customer.id


# ── Checkout session creation ─────────────────────────────────────────────────

def create_subscription_checkout(
    plan: str,
    user: User,
    db: Session,
) -> dict:
    if plan not in PLANS:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {plan}")

    plan_info    = PLANS[plan]
    price_id     = _get_price_id(plan_info["price_id_env"])
    customer_id  = get_or_create_stripe_customer(user, db)

    # Build redirect URLs server-side — never trust the client to supply these
    success_url = APP_BASE_URL + "/dashboard?payment=success"
    cancel_url  = APP_BASE_URL + "/dashboard?payment=cancelled"

    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url + "&session_id={CHECKOUT_SESSION_ID}",
        cancel_url=cancel_url,
        metadata={"user_id": user.id, "plan": plan},
        subscription_data={"metadata": {"user_id": user.id, "plan": plan}},
        allow_promotion_codes=True,
    )
    return {"checkout_url": session.url, "session_id": session.id}


def create_credit_pack_checkout(
    pack: str,
    user: User,
    db: Session,
) -> dict:
    if pack not in CREDIT_PACKS:
        raise HTTPException(status_code=400, detail=f"Invalid pack: {pack}")

    pack_info    = CREDIT_PACKS[pack]
    price_id     = _get_price_id(pack_info["price_id_env"])
    customer_id  = get_or_create_stripe_customer(user, db)

    # Build redirect URLs server-side — never trust the client to supply these
    success_url = APP_BASE_URL + "/dashboard?payment=success"
    cancel_url  = APP_BASE_URL + "/dashboard?payment=cancelled"

    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        mode="payment",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url + "&session_id={CHECKOUT_SESSION_ID}",
        cancel_url=cancel_url,
        metadata={"user_id": user.id, "pack": pack, "tokens": str(pack_info["tokens"])},
    )
    return {"checkout_url": session.url, "session_id": session.id}


# ── Stripe webhook handler ────────────────────────────────────────────────────

def handle_stripe_webhook(payload: bytes, sig_header: str, db: Session) -> dict:
    """
    Processes Stripe events. This is how the server learns about:
    - New subscriptions (grant access)
    - Renewals (reset credits)
    - Cancellations (downgrade to free)
    - One-time payments (add credits)
    - Failed payments (suspend access after grace period)
    """
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_id   = event["id"]
    event_type = event["type"]
    data_obj   = event["data"]["object"]

    # ── Idempotency check — Stripe can retry deliveries ───────────────────────
    # If we've already processed this event_id, return early without re-applying
    # credits or mutations. This prevents double-credit on Stripe retries.
    already_processed = db.query(StripeEvent).filter(
        StripeEvent.event_id == event_id
    ).first()
    if already_processed:
        logger.info(f"Stripe webhook duplicate (skipped): {event_type} id={event_id}")
        return {"status": "already_processed", "event": event_type}

    # Record the event before processing so concurrent retries are also blocked
    db.add(StripeEvent(event_id=event_id, event_type=event_type))
    db.flush()  # write within the current transaction without committing yet

    logger.info(f"Stripe webhook: {event_type}")

    # ── New subscription activated ────────────────────────────────────────────
    if event_type == "customer.subscription.created":
        _handle_subscription_created(data_obj, db)

    # ── Subscription renewed (monthly) ────────────────────────────────────────
    elif event_type == "invoice.payment_succeeded":
        _handle_invoice_paid(data_obj, db)

    # ── Subscription canceled ─────────────────────────────────────────────────
    elif event_type in ("customer.subscription.deleted", "customer.subscription.updated"):
        _handle_subscription_changed(data_obj, db)

    # ── One-time credit pack purchased ───────────────────────────────────────
    elif event_type == "checkout.session.completed":
        session = data_obj
        if session.get("mode") == "payment":
            _handle_credit_pack_purchased(session, db)

    # ── Payment failed ────────────────────────────────────────────────────────
    elif event_type == "invoice.payment_failed":
        _handle_payment_failed(data_obj, db)

    db.commit()  # commit idempotency record + all mutations together
    return {"status": "processed", "event": event_type}


# ── Webhook sub-handlers ──────────────────────────────────────────────────────

def _find_user_by_stripe_customer(customer_id: str, db: Session) -> Optional[User]:
    return db.query(User).filter(User.stripe_customer_id == customer_id).first()


def _handle_subscription_created(subscription: dict, db: Session):
    user_id = subscription.get("metadata", {}).get("user_id")
    plan    = subscription.get("metadata", {}).get("plan", "basic")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        user = _find_user_by_stripe_customer(subscription.get("customer"), db)
    if not user:
        logger.warning(f"Subscription created but user not found: {user_id}")
        return

    plan_info   = PLANS.get(plan, PLANS["basic"])
    period_end  = datetime.fromtimestamp(
        subscription.get("current_period_end", 0), tz=timezone.utc
    )

    # Update user plan — ALL plans (including Business) get a monthly token cap
    user.plan          = plan
    user.credits       = plan_info["monthly_tokens"]
    user.monthly_limit = plan_info["monthly_tokens"]

    # Create subscription record
    sub = Subscription(
        id=str(uuid.uuid4()),
        user_id=user.id,
        stripe_subscription_id=subscription.get("id"),
        plan=plan,
        status="active",
        current_period_end=period_end,
    )
    db.add(sub)
    # Parent commits — do not call db.commit() here
    logger.info(f"Subscription created: user={user.email} plan={plan}")


def _handle_invoice_paid(invoice: dict, db: Session):
    """Called every billing cycle — reset the user's token credits for all plans."""
    subscription_id = invoice.get("subscription")
    amount_paid     = invoice.get("amount_paid", 0)
    currency        = invoice.get("currency", "usd")

    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == subscription_id
    ).first()

    if sub:
        user = db.query(User).filter(User.id == sub.user_id).first()
        if user:
            plan_info      = PLANS.get(sub.plan, PLANS["basic"])
            user.credits   = plan_info["monthly_tokens"]  # reset credits (all plans)
            sub.status     = "active"

            # Record revenue
            revenue = RevenueRecord(
                id=str(uuid.uuid4()),
                stripe_payment_id=invoice.get("id"),
                user_id=user.id,
                amount_cents=amount_paid,
                currency=currency,
                plan=sub.plan,
                type="subscription",
                status="succeeded",
            )
            db.add(revenue)
            # Parent commits — do not call db.commit() here
            logger.info(f"Invoice paid: user={user.email} amount=${amount_paid/100:.2f}")


def _handle_subscription_changed(subscription: dict, db: Session):
    sub_id = subscription.get("id")
    status = subscription.get("status")

    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == sub_id
    ).first()
    if sub:
        sub.status = status
        if status in ("canceled", "unpaid"):
            sub.canceled_at = datetime.utcnow()
            user = db.query(User).filter(User.id == sub.user_id).first()
            if user:
                user.plan    = "free"
                user.credits = 0
        # Parent commits — do not call db.commit() here
        logger.info(f"Subscription {sub_id} status → {status}")


def _handle_credit_pack_purchased(session: dict, db: Session):
    user_id = session.get("metadata", {}).get("user_id")
    tokens  = int(session.get("metadata", {}).get("tokens", 0))
    pack    = session.get("metadata", {}).get("pack", "")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        user = _find_user_by_stripe_customer(session.get("customer"), db)
    if not user:
        logger.warning(f"Credit pack purchased but user not found: {user_id}")
        return

    user.credits += tokens

    revenue = RevenueRecord(
        id=str(uuid.uuid4()),
        stripe_payment_id=session.get("payment_intent"),
        user_id=user.id,
        amount_cents=session.get("amount_total", 0),
        currency=session.get("currency", "usd"),
        plan=f"pack_{pack}",
        type="credit_pack",
        status="succeeded",
    )
    db.add(revenue)
    # Parent commits — do not call db.commit() here

    logger.info(f"Credit pack: user={user.email} +{tokens} tokens")


def _handle_payment_failed(invoice: dict, db: Session):
    subscription_id = invoice.get("subscription")
    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == subscription_id
    ).first()
    if sub:
        sub.status = "past_due"
        db.commit()
        logger.warning(f"Payment failed for subscription {subscription_id}")


# ── Revenue reporting helpers ─────────────────────────────────────────────────

def get_total_revenue(db: Session) -> dict:
    """Returns lifetime and monthly revenue stats for the owner dashboard."""
    from sqlalchemy import func
    from datetime import date

    now        = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total = db.query(func.sum(RevenueRecord.amount_cents)).filter(
        RevenueRecord.status == "succeeded"
    ).scalar() or 0

    monthly = db.query(func.sum(RevenueRecord.amount_cents)).filter(
        RevenueRecord.status == "succeeded",
        RevenueRecord.created_at >= month_start,
    ).scalar() or 0

    count = db.query(func.count(User.id)).filter(User.plan != "free").scalar() or 0

    return {
        "total_revenue_usd":   round(total / 100, 2),
        "monthly_revenue_usd": round(monthly / 100, 2),
        "paying_customers":    count,
    }
