"""Stripe billing, subscription fulfillment, and generation-pack fulfillment."""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import stripe
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .database import User, Subscription, RevenueRecord, StripeEvent, UserEntitlement

logger = logging.getLogger(__name__)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")

# Canonical plan registry. Every billing operation uses these exact identifiers.
PLANS = {
    "free": {
        "name": "Test Drive",
        "monthly_generations": 5,
        "price_usd": 0,
        "connectors_allowed": 1,
        "automation_features_allowed": 1,
        "features": [
            "5 monthly campaigns",
            "1 connector of choice",
            "Core engine preview"
        ],
    },
    "boutique": {
        "name": "Boutique Store",
        "price_id_env": "STRIPE_PRICE_BOUTIQUE",
        "monthly_generations": 150,
        "price_usd": 179.49,
        "connectors_allowed": 2,
        "automation_features_allowed": 1,
        "features": [
            "150 monthly campaigns",
            "2 connectors of choice",
            "1 automation feature (CSV or Auto-Sync)",
            "Email support"
        ],
    },
    "standard": {
        "name": "Standard Store",
        "price_id_env": "STRIPE_PRICE_STANDARD",
        "monthly_generations": 1000,
        "price_usd": 379.49,
        "connectors_allowed": 10,
        "automation_features_allowed": 2,
        "features": [
            "1,000 monthly campaigns",
            "10 connectors of choice",
            "2 automation features",
            "Priority generation speed"
        ],
    },
    "megastore": {
        "name": "Megastore Infrastructure",
        "price_id_env": "STRIPE_PRICE_MEGASTORE",
        "monthly_generations": 2500,
        "price_usd": 9639.63,
        "connectors_allowed": 999,
        "automation_features_allowed": 999,
        "byok_unlimited": True,
        "features": [
            "2,500 monthly campaigns (using our API)",
            "Unlimited campaigns with your own AI API key (BYOK)",
            "All native and custom connectors included",
            "All automation engines and review miners",
            "Dedicated high-throughput cluster",
            "24/7 VIP priority support"
        ],
    },
}

ADD_ONS = {
    "brand_voice_training": {
        "name": "Brand Voice Training (Custom AI Persona)",
        "price_usd": 49.00,
        "billing_type": "one_time",
        "description": "Unlock custom AI persona training with bespoke voice guidelines, target audience tuning, and past copy style transfer.",
        "features": [
            "Bespoke brand persona configuration",
            "Automatic prompt injection on all copy generations",
            "Audience tone and vocabulary matching",
            "Style transfer from your past winning listings"
        ]
    },
    "marketplace_optimizer_pack": {
        "name": "Marketplace Listing Optimizer Pack (50 Listings)",
        "price_usd": 29.00,
        "billing_type": "one_time",
        "description": "Deep algorithmic optimization for Amazon (backend keywords/bullets), Etsy (13 tags/character caps), and Shopify product pages.",
        "features": [
            "Amazon keyword and bullet optimization",
            "Etsy 13-tag high conversion extractor",
            "Shopify SEO meta titles and structured descriptions",
            "Listing compliance and character limit scoring"
        ]
    },
    "done_for_you_marketing_pack": {
        "name": "Done-For-You Monthly Marketing Pack",
        "price_usd": 149.00,
        "billing_type": "monthly",
        "description": "Autonomous full-funnel marketing package containing 4 SEO articles, 10 multi-channel social posts, 3 email drips, and 5 product descriptions.",
        "features": [
            "4 SEO Authority Blog Posts published directly to your store",
            "10 High-converting social media bundles",
            "3 Multi-step customer retention email campaigns",
            "5 Optimized product catalog descriptions"
        ]
    },
    "bulk_catalog_import_pass": {
        "name": "Unlimited Bulk Catalog Import and Semantic Mapper",
        "price_usd": 19.00,
        "billing_type": "one_time",
        "description": "Unlimited CSV, Excel, and Shopify direct catalog imports with automatic AI column mapping and batch rewriting.",
        "features": [
            "Unlimited products per CSV batch",
            "Automated fuzzy column detection",
            "Batch formatting for multiple channels",
            "Direct Shopify catalog 1-click sync"
        ]
    }
}

ONE_TIME_GENERATIONS = {
    "starter": {"name": "Starter Pack (250 generations)", "price_id_env": "STRIPE_PRICE_PACK_STARTER", "generations": 250, "price_usd": 5},
    "growth": {"name": "Growth Pack (1,000 generations)", "price_id_env": "STRIPE_PRICE_PACK_GROWTH", "generations": 1000, "price_usd": 15},
    "scale": {"name": "Scale Pack (3,000 generations)", "price_id_env": "STRIPE_PRICE_PACK_SCALE", "generations": 3000, "price_usd": 40},
}


def _get_price_id(env_var: str) -> str:
    price_id = os.getenv(env_var, "")
    if not price_id:
        raise HTTPException(status_code=503, detail=f"Billing not configured. Set {env_var} in environment variables.")
    return price_id


def get_or_create_stripe_customer(user: User, db: Session) -> str:
    if user.stripe_customer_id:
        return user.stripe_customer_id
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Stripe is not configured")
    customer = stripe.Customer.create(email=user.email, name=user.full_name or "", metadata={"user_id": user.id})
    user.stripe_customer_id = customer.id
    db.commit()
    return customer.id


def create_subscription_checkout(plan: str, user: User, db: Session) -> dict:
    if plan not in PLANS or plan == "free":
        raise HTTPException(status_code=400, detail=f"Invalid paid plan: {plan}")
    info = PLANS[plan]
    customer_id = get_or_create_stripe_customer(user, db)
    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{"price": _get_price_id(info["price_id_env"]), "quantity": 1}],
        success_url=f"{APP_BASE_URL}/dashboard?payment=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{APP_BASE_URL}/dashboard?payment=cancelled",
        metadata={"user_id": user.id, "plan": plan},
        subscription_data={"metadata": {"user_id": user.id, "plan": plan}},
        allow_promotion_codes=True,
    )
    return {"checkout_url": session.url, "session_id": session.id}


def create_one_time_checkout(pack: str, user: User, db: Session) -> dict:
    if pack not in ONE_TIME_GENERATIONS:
        raise HTTPException(status_code=400, detail=f"Invalid pack: {pack}")
    info = ONE_TIME_GENERATIONS[pack]
    customer_id = get_or_create_stripe_customer(user, db)
    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        mode="payment",
        line_items=[{"price": _get_price_id(info["price_id_env"]), "quantity": 1}],
        success_url=f"{APP_BASE_URL}/dashboard?payment=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{APP_BASE_URL}/dashboard?payment=cancelled",
        metadata={"user_id": user.id, "pack": pack, "generations": str(info["generations"])},
    )
    return {"checkout_url": session.url, "session_id": session.id}


def handle_stripe_webhook(payload: bytes, sig_header: str, db: Session) -> dict:
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Stripe webhook secret is not configured")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook")

    event_id = event["id"]
    event_type = event["type"]
    data_obj = event["data"]["object"]

    if db.query(StripeEvent).filter(StripeEvent.event_id == event_id).first():
        return {"status": "already_processed", "event": event_type}

    db.add(StripeEvent(event_id=event_id, event_type=event_type))
    db.flush()

    if event_type == "customer.subscription.created":
        _handle_subscription_created(data_obj, db)
    elif event_type == "invoice.payment_succeeded":
        _handle_invoice_paid(data_obj, db)
    elif event_type in ("customer.subscription.deleted", "customer.subscription.updated"):
        _handle_subscription_changed(data_obj, db)
    elif event_type == "checkout.session.completed" and data_obj.get("mode") == "payment":
        _handle_one_time_purchased(data_obj, db)
    elif event_type == "invoice.payment_failed":
        _handle_payment_failed(data_obj, db)

    db.commit()
    return {"status": "processed", "event": event_type}


def _find_user_by_stripe_customer(customer_id: Optional[str], db: Session) -> Optional[User]:
    if not customer_id:
        return None
    return db.query(User).filter(User.stripe_customer_id == customer_id).first()


def _handle_subscription_created(subscription: dict, db: Session):
    user_id = subscription.get("metadata", {}).get("user_id")
    plan = subscription.get("metadata", {}).get("plan")
    if plan not in PLANS or plan == "free":
        logger.error("Rejected subscription with invalid plan: %r", plan)
        return

    user = db.query(User).filter(User.id == user_id).first() or _find_user_by_stripe_customer(subscription.get("customer"), db)
    if not user:
        logger.error("Subscription created but user not found: %s", user_id)
        return

    info = PLANS[plan]
    period_end_ts = subscription.get("current_period_end")
    period_end = datetime.fromtimestamp(period_end_ts, tz=timezone.utc) if period_end_ts else None
    user.plan = plan
    user.monthly_limit = info["monthly_generations"]
    user.monthly_generations = info["monthly_generations"]
    user.generations = user.monthly_generations + (user.purchased_generations or 0)

    existing = db.query(Subscription).filter(Subscription.stripe_subscription_id == subscription.get("id")).first()
    if existing:
        existing.plan = plan
        existing.status = subscription.get("status", "active")
        existing.current_period_end = period_end
    else:
        db.add(Subscription(
            id=str(uuid.uuid4()), user_id=user.id,
            stripe_subscription_id=subscription.get("id"), plan=plan,
            status=subscription.get("status", "active"), current_period_end=period_end,
        ))


def _handle_invoice_paid(invoice: dict, db: Session):
    subscription_id = invoice.get("subscription")
    if not subscription_id:
        return
    sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == subscription_id).first()
    if not sub or sub.plan not in PLANS:
        return
    user = db.query(User).filter(User.id == sub.user_id).first()
    if not user:
        return

    info = PLANS[sub.plan]
    user.monthly_limit = info["monthly_generations"]
    user.monthly_generations = info["monthly_generations"]
    user.generations = info["monthly_generations"] + (user.purchased_generations or 0)
    sub.status = "active"

    payment_id = invoice.get("id")
    if payment_id and not db.query(RevenueRecord).filter(RevenueRecord.stripe_payment_id == payment_id).first():
        db.add(RevenueRecord(
            id=str(uuid.uuid4()), stripe_payment_id=payment_id, user_id=user.id,
            amount_cents=invoice.get("amount_paid", 0), currency=invoice.get("currency", "usd"),
            plan=sub.plan, type="subscription", status="succeeded",
        ))


def _handle_subscription_changed(subscription: dict, db: Session):
    sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == subscription.get("id")).first()
    if not sub:
        return
    status = subscription.get("status", sub.status)
    sub.status = status
    period_end_ts = subscription.get("current_period_end")
    if period_end_ts:
        sub.current_period_end = datetime.fromtimestamp(period_end_ts, tz=timezone.utc)

    if status in ("canceled", "unpaid"):
        sub.canceled_at = datetime.utcnow()
        user = db.query(User).filter(User.id == sub.user_id).first()
        if user:
            user.plan = "free"
            user.monthly_limit = PLANS["free"]["monthly_generations"]
            user.monthly_generations = PLANS["free"]["monthly_generations"]
            user.generations = user.monthly_generations + (user.purchased_generations or 0)


def _handle_one_time_purchased(session: dict, db: Session):
    metadata = session.get("metadata") or {}
    user_id = metadata.get("user_id")
    pack = metadata.get("pack")
    addon_key = metadata.get("addon_key")

    user = db.query(User).filter(User.id == user_id).first() or _find_user_by_stripe_customer(session.get("customer"), db)
    if not user:
        logger.error("One-time purchase fulfillment failed: user not found: %s", user_id)
        return

    payment_id = session.get("payment_intent") or session.get("id")

    if pack and pack in ONE_TIME_GENERATIONS:
        generations = ONE_TIME_GENERATIONS[pack]["generations"]
        user.purchased_generations = (user.purchased_generations or 0) + generations
        user.generations += generations
        if payment_id and not db.query(RevenueRecord).filter(RevenueRecord.stripe_payment_id == payment_id).first():
            db.add(RevenueRecord(
                id=str(uuid.uuid4()), stripe_payment_id=payment_id, user_id=user.id,
                amount_cents=session.get("amount_total", 0), currency=session.get("currency", "usd"),
                plan=f"one_time_{pack}", type="generation_pack", status="succeeded",
            ))
        logger.info("Generation pack fulfilled: user=%s +%s generations (total purchased=%s)", user.email, generations, user.purchased_generations)
    elif addon_key and addon_key in ADD_ONS:
        addon = ADD_ONS[addon_key]
        if payment_id and not db.query(RevenueRecord).filter(RevenueRecord.stripe_payment_id == payment_id).first():
            db.add(RevenueRecord(
                id=str(uuid.uuid4()), stripe_payment_id=payment_id, user_id=user.id,
                amount_cents=session.get("amount_total", int(addon["price_usd"] * 100)),
                currency=session.get("currency", "usd"),
                plan=f"addon_{addon_key}", type="addon", status="succeeded",
            ))
        
        # Grant feature entitlement
        ent = db.query(UserEntitlement).filter(
            UserEntitlement.user_id == user.id,
            UserEntitlement.entitlement_key == addon_key
        ).first()
        if ent:
            ent.active = True
        else:
            db.add(UserEntitlement(
                id=str(uuid.uuid4()),
                user_id=user.id,
                entitlement_key=addon_key,
                entitlement_type="addon",
                active=True
            ))
        logger.info("Addon fulfilled & entitlement granted: user=%s addon=%s", user.email, addon_key)


def _handle_payment_failed(invoice: dict, db: Session):
    subscription_id = invoice.get("subscription")
    sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == subscription_id).first()
    if sub:
        sub.status = "past_due"
        logger.warning("Payment failed for subscription %s", subscription_id)


def get_total_revenue(db: Session) -> dict:
    from sqlalchemy import func
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = db.query(func.sum(RevenueRecord.amount_cents)).filter(RevenueRecord.status == "succeeded").scalar() or 0
    monthly = db.query(func.sum(RevenueRecord.amount_cents)).filter(
        RevenueRecord.status == "succeeded", RevenueRecord.created_at >= month_start
    ).scalar() or 0
    count = db.query(func.count(User.id)).filter(User.plan != "free").scalar() or 0
    return {
        "total_revenue_usd": round(total / 100, 2),
        "monthly_revenue_usd": round(monthly / 100, 2),
        "paying_customers": count,
    }

def user_has_entitlement(user: User, key: str, db: Session) -> bool:
    """
    Returns True if user has access to a specific add-on or feature.
    Paid subscription plans (Boutique, Standard, Megastore) or explicit à-la-carte
    UserEntitlement purchases grant access. Free plan users require an add-on.
    """
    if user.plan in ("boutique", "standard", "megastore"):
        return True
    ent = db.query(UserEntitlement).filter(
        UserEntitlement.user_id == user.id,
        UserEntitlement.entitlement_key == key,
        UserEntitlement.active == True
    ).first()
    return ent is not None
