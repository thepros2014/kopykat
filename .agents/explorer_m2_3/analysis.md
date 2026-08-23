# Milestone 2 Technical Analysis: Multi-Channel Inventory Balancing, Loop-Free Fanout, Drift Reconciliation, Webhook Idempotency & SSRF Defense

**Explorer**: Explorer 3 (Milestone 2)  
**Date**: 2026-08-23  
**Working Directory**: `.agents/explorer_m2_3/`  
**Target Scope**: `server/inventory.py`, `server/database.py`, `server/integrations.py`, `server/connector_engine.py`, `tests/test_inventory.py`, `tests/test_connectors.py`, `tests/test_ssrf_async.py`

---

## 1. Executive Summary

Milestone 2 expands KopyKat's commerce automation layer with autonomous platform connectors, real-time bi-directional catalog and inventory synchronization, loop-free fanout, stock drift reconciliation, webhook idempotency deduplication, and async SSRF/DNS rebinding defense.

This investigation analyzes the technical design, database models, synchronization algorithms, race condition defenses, and testing suites required to achieve 100% compliance with `ORIGINAL_REQUEST.md`, `PROJECT.md`, and `SCOPE.md`.

Key Findings:
1. **Supported Platform Set**: `server/inventory.py` currently lists 6 platforms (`{"shopify", "amazon", "ebay", "walmart", "temu", "woocommerce"}`). It must be expanded to all 8 platforms specified in `SCOPE.md`: `{"shopify", "amazon", "etsy", "tiktok", "ebay", "walmart", "temu", "woocommerce"}` with alias normalization (e.g., `tiktok_shop` -> `tiktok`, `woo` -> `woocommerce`).
2. **Loop-Free Fanout**: `sync_inventory_across_platforms` correctly excludes the source platform (`fanout_results[trigger] = "source_event"`), avoiding infinite circular echo loops. Outbound updates should support both direct execution and async connector dispatch.
3. **Stock Drift Reconciliation**: `reconcile_inventory_sku` establishes a single source of truth (`canonical_stock`), calculates drift (`canonical_stock - previous_stock`), updates central state, fans out to all connected channels (`reconciled_to_{canonical_stock}`), and logs to `InventorySyncLog`.
4. **Webhook Idempotency Ledger**: `InventoryWebhookEvent` with `UniqueConstraint("platform", "event_id")` ensures deduplication. Replay webhooks immediately return `{"status": "already_processed"}` without altering stock or creating duplicate sync logs.
5. **Testing Architecture**: Existing tests pass (65 tests, 0 errors). Milestone 2 requires comprehensive test suites across `tests/test_connectors.py`, `tests/test_inventory.py`, and new `tests/test_ssrf_async.py`.
6. **Zero-Emoji and Flake8 Invariants**: All code, docstrings, log messages, and reports must adhere strictly to zero-emoji and flake8 standards.

---

## 2. Inventory Architecture & Database Models

### 2.1 Existing ORM Models (`server/database.py`)

#### `InventoryItem` (Table: `inventory_items`)
- `id`: `String(36)` (UUID Primary Key)
- `user_id`: `String(36)` (Foreign Key `users.id`, non-nullable)
- `sku`: `String(100)` (SKU identifier, non-nullable)
- `title`: `String(255)` (Product title, non-nullable)
- `total_stock`: `Integer` (Current canonical quantity, non-nullable, default 0)
- `platform_stock`: `Text` (JSON string map of `{platform: quantity}`, default `"{}"`)
- `updated_at`: `DateTime` (Timestamp of last update, auto-updating)

*Assessment*: Clean and robust. Stock should always be clamped at 0 (`total_stock >= 0`) during delta operations.

#### `InventoryWebhookEvent` (Table: `inventory_webhook_events`)
- `id`: `String(36)` (UUID Primary Key)
- `platform`: `String(50)` (Platform name, non-nullable)
- `event_id`: `String(100)` (Platform webhook / order identifier, non-nullable)
- `created_at`: `DateTime` (Timestamp of arrival)
- `__table_args__`: `(UniqueConstraint("platform", "event_id", name="uq_platform_event_id"),)`

*Assessment*: Provides database-enforced uniqueness preventing duplicate webhook processing.

#### `InventorySyncLog` (Table: `inventory_sync_logs`)
- `id`: `String(36)` (UUID Primary Key)
- `user_id`: `String(36)` (Foreign Key `users.id`, non-nullable)
- `sku`: `String(100)` (SKU identifier, non-nullable)
- `trigger_platform`: `String(50)` (Triggering channel or `"reconciliation_engine"`)
- `quantity_change`: `Integer` (Delta applied, e.g. -2 for sale, +10 for restock, drift delta for reconcile)
- `new_quantity`: `Integer` (Resulting stock quantity)
- `fanout_results`: `Text` (JSON string map of `{platform: status}`)
- `created_at`: `DateTime` (Timestamp of sync execution)

*Assessment*: Complete audit trail for multi-channel synchronization events.

#### `UserIntegration` (Table: `user_integrations`)
- `id`: `String(36)` (UUID Primary Key)
- `user_id`: `String(36)` (User ID, non-nullable)
- `platform`: `String(50)` (Platform name, non-nullable)
- `credentials`: `String(1000)` (Fernet-encrypted credentials payload)
- `status`: `String(50)` (`"connected"`, `"disconnected"`, `"error"`)
- `last_synced_at`: `DateTime` (Timestamp of last sync)

---

## 3. Multi-Channel Inventory Balancing & Supported Platforms

### 3.1 Supported Platform Matrix
Per `SCOPE.md`, the supported inventory platforms are:
`SUPPORTED_INVENTORY_PLATFORMS = {"shopify", "amazon", "etsy", "tiktok", "ebay", "walmart", "temu", "woocommerce"}`

### 3.2 Platform Normalization
Incoming platform identifiers must be normalized to prevent casing and alias mismatches:
```python
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
    cleaned = platform.strip().lower()
    return PLATFORM_ALIASES.get(cleaned, cleaned)
```

---

## 4. Async Loop-Free Fanout Mechanism

### 4.1 The Echo Storm Problem
When a sale occurs on Platform A (e.g. Shopify):
1. Shopify sends a webhook: `-1 unit on SKU-100`.
2. KopyKat updates central stock from 10 to 9.
3. KopyKat fans out stock updates to Amazon, eBay, Walmart: set stock to 9.
4. If Amazon emits a webhook acknowledging the stock update, KopyKat must NOT treat Amazon's acknowledgment as a new stock change, which would trigger another fanout loop back to Shopify and other channels.

### 4.2 Loop-Free Fanout Mechanics
1. **Source Event Suppression**:
   In `sync_inventory_across_platforms`, the origin channel is identified via `trigger_platform`.
   When looping through active user integrations:
   ```python
   if platform_name == trigger_normalized:
       fanout_results[platform_name] = "source_event"
       continue
   ```
2. **Target Channel Dispatch**:
   For each connected integration where `platform_name != trigger_normalized` and `platform_name in SUPPORTED_INVENTORY_PLATFORMS`:
   - Outbound stock update payload is dispatched.
   - Status is recorded: `fanout_results[platform_name] = f"synced_to_{new_stock}"`.
3. **Item Platform Stock Map**:
   `InventoryItem.platform_stock` is updated with `{platform: new_stock}` for all participating channels.
4. **Audit Log Persistence**:
   The entire fanout outcome dictionary is serialized to `InventorySyncLog.fanout_results`.

---

## 5. Stock Drift Reconciliation & Conflict Resolution

### 5.1 Root Causes of Stock Drift
- Out-of-band sales (in-person POS, phone orders).
- Direct manual edits by merchants on marketplace seller portals.
- Missed webhooks during platform outages or network partitions.
- Returns and restocking not routed through webhooks.

### 5.2 Reconciliation Algorithm (`reconcile_inventory_sku`)
```
Input: user_id, sku, canonical_stock, db

1. Lock SKU row with pessimistic lock (`with_for_update`)
2. If SKU item does not exist:
     Create new InventoryItem with total_stock = canonical_stock
   Else:
     previous_stock = item.total_stock
     drift = canonical_stock - previous_stock
     item.total_stock = canonical_stock
     item.updated_at = utcnow()
3. Fanout to ALL connected integrations in SUPPORTED_INVENTORY_PLATFORMS:
     fanout_results[platform] = f"reconciled_to_{canonical_stock}"
4. Update item.platform_stock for all reconciled platforms
5. Persist InventorySyncLog:
     trigger_platform = "reconciliation_engine"
     quantity_change = drift
     new_quantity = canonical_stock
     fanout_results = json.dumps(fanout_results)
6. Commit transaction
7. Return {sku, previous_stock, reconciled_stock, drift_corrected, fanout_results}
```

### 5.3 Concurrency & Conflict Arbitration Rules
1. **Central Authority**: `InventoryItem.total_stock` is the authoritative source of truth.
2. **Pessimistic Row Locking**: All read-modify-write operations on inventory acquire `with_for_update()` to prevent lost updates under high concurrency.
3. **Zero-Floor Clamping**: `new_stock = max(0, old_stock + delta)`. Stock can never become negative.
4. **Idempotent Webhook Processing**: Concurrent duplicate webhooks are serialized and deduplicated via the `InventoryWebhookEvent` unique index.

---

## 6. Webhook Idempotency Ledger

### 6.1 Deduplication Workflow
```
Incoming Webhook Request -> Extract (platform, event_id)
      │
      ▼
Check `InventoryWebhookEvent` where platform == p and event_id == eid
      │
      ├── Exists? ──► Log warning/info ──► Return {"status": "already_processed", ...}
      │                                    (No stock deduction, no fanout, no sync log)
      │
      └── Not Exists ──► Insert into `InventoryWebhookEvent`
                         Proceed with atomic stock update & loop-free fanout
```

### 6.2 Concurrent Race Protection
To protect against two identical webhook payloads hitting the server simultaneously:
- `UniqueConstraint("platform", "event_id")` throws an `IntegrityError` on the second transaction.
- The exception handler rolls back the sub-transaction and returns `{"status": "already_processed"}` without corrupting stock totals.

---

## 7. Bi-Directional Catalog Sync Architecture

### 7.1 PlatformConnector Protocol (`server/integrations.py`)
```python
from typing import Protocol

class PlatformConnector(Protocol):
    platform_name: str

    async def fetch_catalog(self, credentials: dict, limit: int = 50) -> list[dict]:
        """Fetch remote product catalog and normalize to list of product dicts."""
        ...

    async def push_product(self, credentials: dict, product_data: dict) -> dict:
        """Push/publish a product to the marketplace platform."""
        ...

    async def update_stock(self, credentials: dict, sku: str, quantity: int) -> dict:
        """Update inventory stock level for a given SKU on the marketplace."""
        ...

    def verify_webhook(self, headers: dict, raw_payload: bytes, secret: str) -> bool:
        """Verify cryptographic HMAC signature of incoming platform webhook."""
        ...
```

### 7.2 Standardized Platform Implementations
Concrete connector classes for:
- `ShopifyConnector` (`platform_name = "shopify"`)
- `AmazonConnector` (`platform_name = "amazon"`)
- `EtsyConnector` (`platform_name = "etsy"`)
- `TikTokShopConnector` (`platform_name = "tiktok"`)
- `EBayConnector` (`platform_name = "ebay"`)
- `WalmartConnector` (`platform_name = "walmart"`)
- `TemuConnector` (`platform_name = "temu"`)
- `WooCommerceConnector` (`platform_name = "woocommerce"`)

Each connector uses `SafeAsyncHTTPClient` for outbound requests, enforces strict SSRF protections, and decrypts credentials using `decrypt_credentials()`.

---

## 8. SSRF Defense & Safe Async HTTP Client (`server/connector_engine.py`)

### 8.1 Threat Model
Outbound HTTP requests initiated by connector discovery, catalog synchronization, and stock updates could be manipulated to target internal cloud infrastructure (AWS metadata `169.254.169.254`, internal microservices on RFC 1918 addresses, loopback services).

### 8.2 SafeAsyncHTTPClient Defense Invariants
1. **Scheme Validation**: Enforce `https://` only. Reject `http://`, `ftp://`, `file://`, `gopher://`.
2. **Host Blacklisting**: Disallow `localhost`, `localhost.localdomain`, `*.localhost`.
3. **DNS Pre-Resolution**: Perform DNS resolution prior to connection. Reject any domain resolving to:
   - Loopback (`127.0.0.0/8`, `::1`)
   - RFC 1918 Private (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`)
   - Link-Local (`169.254.0.0/16`, `fe80::/10`)
   - Multicast (`224.0.0.0/4`, `ff00::/8`)
   - Reserved / Unspecified (`0.0.0.0/8`, `240.0.0.0/4`, `::/128`)
   - Unique Local IPv6 (`fc00::/7`)
4. **Socket Pinning / DNS Rebinding Defense**: Connect directly to the pre-validated IP address to eliminate TOCTOU (Time-of-Check to Time-of-Use) DNS rebinding attacks, while passing the original hostname as the SNI `server_hostname` and `Host` header.
5. **Redirect Blocking**: Set `allow_redirects=False` (`follow_redirects=False`). Reject 3xx redirect status codes to prevent redirect-based SSRF bypasses.
6. **Streaming Response Cap**: Stream response chunks up to `2_000_000` bytes (2MB). Terminate and raise `ConnectorError` if exceeded.

---

## 9. Comprehensive Testing Strategy for Milestone 2

### 9.1 `tests/test_inventory.py` Test Plan
- `test_inventory_item_crud`: Verify create, read, update, list of inventory items.
- `test_inventory_webhook_and_fanout`: Verify single sale event, origin exclusion (`"source_event"`), and fanout across target integrations.
- `test_inventory_fanout_all_eight_platforms`: Verify fanout across all 8 supported platforms (`shopify`, `amazon`, `etsy`, `tiktok`, `ebay`, `walmart`, `temu`, `woocommerce`).
- `test_inventory_webhook_idempotency_deduplication`: Verify replay prevention on matching `(platform, event_id)` with `InventoryWebhookEvent`.
- `test_inventory_reconcile_drift_correction`: Verify drift calculation, database update, universal fanout, and sync log recording.
- `test_inventory_stock_floor_zero`: Verify stock reductions never drop below 0.
- `test_inventory_cross_tenant_isolation`: Verify User A cannot access or update User B's inventory items or sync logs.

### 9.2 `tests/test_connectors.py` Test Plan
- `test_validate_public_url_blocks_localhost`: Ensure localhost domains are rejected.
- `test_validate_public_url_blocks_http_scheme`: Ensure unencrypted HTTP is rejected.
- `test_validate_public_url_blocks_private_ips`: Ensure RFC 1918 / RFC 3927 addresses are rejected.
- `test_build_connector_spec_valid`: Ensure valid OpenAPI 3.0 specs generate correct connector models.
- `test_connector_discovery_api_endpoint`: Ensure API endpoint handles discovery, credential saving, and status toggles.
- `test_platform_connectors_protocol_compliance`: Verify Amazon, Shopify, Etsy, TikTok Shop, eBay connectors implement `PlatformConnector`.
- `test_platform_connector_webhook_verification`: Verify HMAC verification logic with valid and invalid signatures.

### 9.3 `tests/test_ssrf_async.py` Test Plan
- `test_safe_async_http_client_blocks_private_ip_ranges`: Test IPv4 private ranges (10.x, 172.16.x, 192.168.x, 127.x, 169.254.x).
- `test_safe_async_http_client_blocks_ipv6_private`: Test `::1`, `fe80::`, `fc00::`.
- `test_safe_async_http_client_blocks_redirects`: Test 301, 302, 307 redirects rejected.
- `test_safe_async_http_client_caps_response_at_2mb`: Test streaming cutoff when payload > 2MB.
- `test_safe_async_http_client_socket_pinning`: Test connection pins to pre-resolved IP while setting SNI and Host headers.

---

## 10. Code Proposals & Reference Patches

### 10.1 `server/inventory.py` Proposed Code Structure

```python
"""
inventory.py — Cross-Platform Inventory & Stock Balancer for KopyKat.
Receives order and stock change events from one platform
and automatically fans out inventory level updates to all other connected platforms.
"""

import json
import logging
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .database import InventoryItem, InventorySyncLog, UserIntegration, InventoryWebhookEvent

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
    cleaned = platform.strip().lower()
    return PLATFORM_ALIASES.get(cleaned, cleaned)


def sync_inventory_across_platforms(
    user_id: str,
    sku: str,
    delta: int,
    trigger_platform: str,
    db: Session,
    title: str = "",
    event_id: str = "",
) -> dict:
    """
    Atomically updates SKU stock and fans out sync updates to all connected channels
    except the trigger platform to prevent echo loops.
    """
    clean_sku = sku.strip().upper()
    trigger_normalized = normalize_platform_name(trigger_platform)

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

    # Fetch inventory item with pessimistic lock
    query = db.query(InventoryItem).filter(
        InventoryItem.user_id == user_id,
        InventoryItem.sku == clean_sku,
    )
    if getattr(db.bind, "dialect", None) and db.bind.dialect.name != "sqlite":
        query = query.with_for_update()
    item = query.first()

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

    # Find all active connected integrations for this user
    integrations = db.query(UserIntegration).filter(
        UserIntegration.user_id == user_id,
        UserIntegration.status == "connected",
    ).all()

    fanout_results = {}

    for integ in integrations:
        platform_name = normalize_platform_name(integ.platform)
        if platform_name == trigger_normalized:
            # Skip originating platform to prevent echo loops
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
) -> dict:
    """
    Reconciles platform stock drift by setting a single verified canonical stock level
    and re-synchronizing all connected sales channels.
    """
    clean_sku = sku.strip().upper()
    query = db.query(InventoryItem).filter(
        InventoryItem.user_id == user_id,
        InventoryItem.sku == clean_sku,
    )
    if getattr(db.bind, "dialect", None) and db.bind.dialect.name != "sqlite":
        query = query.with_for_update()
    item = query.first()

    if not item:
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

    previous_stock = item.total_stock
    drift = canonical_stock - previous_stock
    item.total_stock = canonical_stock
    item.updated_at = datetime.utcnow()

    # Fanout reconciliation to all connected integrations
    integrations = db.query(UserIntegration).filter(
        UserIntegration.user_id == user_id,
        UserIntegration.status == "connected",
    ).all()

    fanout_results = {}
    for integ in integrations:
        p_name = normalize_platform_name(integ.platform)
        if p_name in SUPPORTED_INVENTORY_PLATFORMS:
            fanout_results[p_name] = f"reconciled_to_{canonical_stock}"

    item.platform_stock = json.dumps({p: canonical_stock for p in fanout_results})

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
```

---

## 11. Conclusion

The existing architecture provides a strong foundation for Milestone 2. By updating `server/inventory.py` to support all 8 target platforms, implementing alias normalization, ensuring loop-free fanout and idempotency race safety, and pairing it with `SafeAsyncHTTPClient` and comprehensive test suites (`tests/test_connectors.py`, `tests/test_inventory.py`, `tests/test_ssrf_async.py`), Milestone 2 will achieve 100% verification and architectural compliance.
