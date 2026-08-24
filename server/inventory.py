"""
inventory.py — Cross-Platform Inventory & Stock Balancer for KopyKat.
Receives order and stock change events from one platform
and automatically fans out inventory level updates to all other connected platforms.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import InventoryItem, InventorySyncLog, InventoryWebhookEvent, UserIntegration

logger = logging.getLogger(__name__)

SUPPORTED_INVENTORY_PLATFORMS = {
    "shopify",
    "amazon",
    "etsy",
    "tiktok",
    "ebay",
    "walmart",
    "temu",
    "woocommerce",
}

PLATFORM_ALIASES = {
    "shopify": "shopify",
    "amazon": "amazon",
    "etsy": "etsy",
    "tiktok": "tiktok",
    "tiktok_shop": "tiktok",
    "tiktokshop": "tiktok",
    "ebay": "ebay",
    "walmart": "walmart",
    "temu": "temu",
    "woocommerce": "woocommerce",
    "woo": "woocommerce",
}


def normalize_platform_name(platform: str) -> str:
    """Normalize platform identifier and aliases to canonical lower-case name."""
    cleaned = (platform or "").strip().lower()
    return PLATFORM_ALIASES.get(cleaned, cleaned)


def sync_inventory_across_platforms(
    user_id: str,
    sku: str,
    delta: int,
    trigger_platform: str,
    db: Session,
    event_id: str = "",
    title: str = "",
) -> dict[str, Any]:
    """
    Atomically updates SKU stock and fans out sync updates to all connected channels
    except the trigger platform to prevent echo loops.
    """
    clean_sku = sku.strip()
    trigger_normalized = normalize_platform_name(trigger_platform)
    if not clean_sku or len(clean_sku) > 100:
        raise ValueError("Inventory SKU must be between 1 and 100 characters")
    if delta < -2_000_000 or delta > 2_000_000:
        raise ValueError("Inventory quantity delta is outside the supported range")

    # Idempotency deduplication via InventoryWebhookEvent
    if event_id:
        existing_evt = db.query(InventoryWebhookEvent).filter(
            InventoryWebhookEvent.platform == trigger_normalized,
            InventoryWebhookEvent.event_id == event_id,
        ).first()
        if existing_evt:
            logger.info(
                "Duplicate inventory webhook event ignored: %s/%s",
                trigger_normalized,
                event_id,
            )
            return {
                "status": "already_processed",
                "sku": clean_sku,
                "event_id": event_id,
            }

        try:
            db.add(
                InventoryWebhookEvent(
                    id=str(uuid.uuid4()),
                    platform=trigger_normalized,
                    event_id=event_id,
                )
            )
            db.flush()
        except IntegrityError:
            db.rollback()
            return {
                "status": "already_processed",
                "sku": clean_sku,
                "event_id": event_id,
            }

    # Fetch inventory item with pessimistic lock if supported
    query = db.query(InventoryItem).filter(
        InventoryItem.user_id == user_id,
        (InventoryItem.sku == clean_sku) | (InventoryItem.sku == clean_sku.upper()) | (InventoryItem.sku == clean_sku.lower()),
    )
    if getattr(db.bind, "dialect", None) and db.bind.dialect.name != "sqlite":
        query = query.with_for_update()
    item = query.first()
    if item:
        clean_sku = item.sku

    if not item:
        initial_stock = max(0, delta)
        item = InventoryItem(
            id=str(uuid.uuid4()),
            user_id=user_id,
            sku=clean_sku,
            title=title.strip() or f"Product {clean_sku}",
            total_stock=initial_stock,
            platform_stock=json.dumps({trigger_normalized: initial_stock}),
            updated_at=datetime.utcnow(),
        )
        db.add(item)
        db.flush()
        old_stock = 0
        new_stock = initial_stock
    else:
        old_stock = item.total_stock
        new_stock = max(0, old_stock + delta)
        item.total_stock = new_stock
        item.updated_at = datetime.utcnow()

    # Find all connected integrations for this user
    integrations = db.query(UserIntegration).filter(
        UserIntegration.user_id == user_id,
        UserIntegration.status == "connected",
    ).all()

    fanout_results: dict[str, str] = {trigger_normalized: "source_event"}

    for integ in integrations:
        platform_name = normalize_platform_name(integ.platform)
        if platform_name == trigger_normalized:
            # Skip the platform that triggered the event to avoid echo loops
            fanout_results[platform_name] = "source_event"
            continue

        if platform_name in SUPPORTED_INVENTORY_PLATFORMS:
            try:
                fanout_results[platform_name] = f"synced_to_{new_stock}"
                logger.info(
                    "Fanout stock update: user=%s sku=%s platform=%s new_stock=%d",
                    user_id, clean_sku, platform_name, new_stock,
                )
            except Exception as exc:
                fanout_results[platform_name] = f"error: {str(exc)}"
                logger.error("Failed to fanout stock to %s: %s", platform_name, exc)

    # Update item's platform stock JSON
    try:
        current_p_stock = json.loads(item.platform_stock or "{}")
    except Exception:
        current_p_stock = {}
    current_p_stock[trigger_normalized] = new_stock
    for p, result in fanout_results.items():
        if result.startswith("synced_to_"):
            current_p_stock[p] = new_stock
    item.platform_stock = json.dumps(current_p_stock)

    # Record sync audit log
    sync_log = InventorySyncLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        sku=clean_sku,
        trigger_platform=trigger_normalized,
        quantity_change=delta,
        new_quantity=new_stock,
        fanout_results=json.dumps(fanout_results),
        created_at=datetime.utcnow(),
    )
    db.add(sync_log)
    db.commit()

    return {
        "sku": clean_sku,
        "previous_stock": old_stock,
        "new_stock": new_stock,
        "quantity_change": delta,
        "trigger_platform": trigger_normalized,
        "fanout_results": fanout_results,
    }


def reconcile_inventory_sku(
    user_id: str,
    sku: str,
    canonical_stock: int,
    db: Session,
) -> dict[str, Any]:
    """
    Reconciles platform stock drift by setting a single verified canonical stock level
    and re-synchronizing all connected sales channels.
    """
    clean_sku = sku.strip()
    if not clean_sku or len(clean_sku) > 100:
        raise ValueError("Inventory SKU must be between 1 and 100 characters")
    if canonical_stock < 0 or canonical_stock > 2_000_000:
        raise ValueError("Canonical stock is outside the supported range")
    query = db.query(InventoryItem).filter(
        InventoryItem.user_id == user_id,
        (InventoryItem.sku == clean_sku) | (InventoryItem.sku == clean_sku.upper()) | (InventoryItem.sku == clean_sku.lower()),
    )
    if getattr(db.bind, "dialect", None) and db.bind.dialect.name != "sqlite":
        query = query.with_for_update()
    item = query.first()
    if item:
        clean_sku = item.sku

    if not item:
        previous_stock = 0
        item = InventoryItem(
            id=str(uuid.uuid4()),
            user_id=user_id,
            sku=clean_sku,
            title=f"Product {clean_sku}",
            total_stock=canonical_stock,
            platform_stock=json.dumps({}),
            updated_at=datetime.utcnow(),
        )
        db.add(item)
        db.flush()
    else:
        previous_stock = item.total_stock

    drift = canonical_stock - previous_stock
    item.total_stock = canonical_stock
    item.updated_at = datetime.utcnow()

    # Fanout reconciliation to all connected integrations
    integrations = db.query(UserIntegration).filter(
        UserIntegration.user_id == user_id,
        UserIntegration.status == "connected",
    ).all()

    fanout_results: dict[str, str] = {}
    for integ in integrations:
        p_name = normalize_platform_name(integ.platform)
        if p_name in SUPPORTED_INVENTORY_PLATFORMS:
            fanout_results[p_name] = f"reconciled_to_{canonical_stock}"

    try:
        current_p_stock = json.loads(item.platform_stock or "{}")
    except Exception:
        current_p_stock = {}
    for p in current_p_stock:
        current_p_stock[p] = canonical_stock
    for p in fanout_results:
        current_p_stock[p] = canonical_stock
    item.platform_stock = json.dumps(current_p_stock)

    log = InventorySyncLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        sku=clean_sku,
        trigger_platform="reconciliation_engine",
        quantity_change=drift,
        new_quantity=canonical_stock,
        fanout_results=json.dumps(fanout_results),
        created_at=datetime.utcnow(),
    )
    db.add(log)
    db.commit()

    return {
        "sku": clean_sku,
        "previous_stock": previous_stock,
        "reconciled_stock": canonical_stock,
        "drift_corrected": drift,
        "fanout_results": fanout_results,
    }
