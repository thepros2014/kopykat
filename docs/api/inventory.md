# API Documentation: Inventory Balancer & Multi-Platform Sync

KopyKat balances stock levels across connected marketplaces in real time. When an order event or quantity adjustment occurs on one channel (e.g. Shopify), KopyKat automatically fans out inventory updates to Amazon, eBay, Walmart, and Temu while skipping the trigger source to prevent infinite echo loops.

---

## 1. List Tracked Inventory SKUs

```http
GET /api/inventory
Authorization: Bearer <API_KEY_OR_TOKEN>
```

### Response (`200 OK`):
```json
[
  {
    "id": "inv_a1b2c3d4-...",
    "sku": "BACKPACK-PRO-01",
    "title": "UltraShield Pro Travel Backpack",
    "total_stock": 48,
    "platform_stock": {
      "shopify": 48,
      "amazon": 48,
      "ebay": 48,
      "walmart": 48
    },
    "updated_at": "2026-08-23T00:00:00Z"
  }
]
```

---

## 2. Register or Adjust SKU Stock

```http
POST /api/inventory/item
Authorization: Bearer <API_KEY_OR_TOKEN>
Content-Type: application/json

{
  "sku": "BACKPACK-PRO-01",
  "title": "UltraShield Pro Travel Backpack",
  "total_stock": 50
}
```

### Response (`200 OK`):
```json
{
  "id": "inv_a1b2c3d4-...",
  "sku": "BACKPACK-PRO-01",
  "title": "UltraShield Pro Travel Backpack",
  "total_stock": 50,
  "platform_stock": {},
  "updated_at": "2026-08-23T00:00:00Z"
}
```

---

## 3. Webhook Stock Ingestion (Order Event)

Store webhook endpoint to paste into Shopify / marketplace notification settings (`orders/create` or `inventory_levels/update`).

```http
POST /api/inventory/webhook/shopify
Authorization: Bearer <API_KEY_OR_TOKEN>
Content-Type: application/json

{
  "sku": "BACKPACK-PRO-01",
  "quantity_delta": -1,
  "order_id": "sh_order_99881",
  "customer_email": "buyer@example.com"
}
```

### Response (`200 OK`):
```json
{
  "sku": "BACKPACK-PRO-01",
  "previous_stock": 50,
  "new_stock": 49,
  "quantity_change": -1,
  "trigger_platform": "shopify",
  "fanout_results": {
    "shopify": "source_event",
    "amazon": "synced_to_49",
    "ebay": "synced_to_49",
    "walmart": "synced_to_49"
  }
}
```

---

## 4. View Sync Audit Trail

```http
GET /api/inventory/logs
Authorization: Bearer <API_KEY_OR_TOKEN>
```

### Response (`200 OK`):
```json
[
  {
    "id": "log_77a99b-...",
    "sku": "BACKPACK-PRO-01",
    "trigger_platform": "shopify",
    "quantity_change": -1,
    "new_quantity": 49,
    "fanout_results": {
      "shopify": "source_event",
      "amazon": "synced_to_49"
    },
    "created_at": "2026-08-23T00:00:00Z"
  }
]
```
