# Inventory and stock reconciliation

The inventory service stores a user-scoped canonical quantity for each SKU,
records inventory events, and can fan out updates to configured connectors.
Provider writes are credential-dependent and should be tested against
non-production accounts.

## Register or update a SKU

```http
POST /api/inventory/item
Authorization: Bearer <token-or-api-key>
Content-Type: application/json

{
  "sku": "BACKPACK-PRO-01",
  "title": "Travel Backpack",
  "total_stock": 50
}
```

SKUs are normalized to uppercase. The operation creates the item or updates
the authenticated user's existing item with that SKU.

## List inventory

```http
GET /api/inventory
Authorization: Bearer <token-or-api-key>
```

The response includes the canonical total, any persisted platform quantities,
and the update timestamp. Records belonging to another user are not returned.

## Process an inventory event

```http
POST /api/inventory/webhook/shopify
Authorization: Bearer <token-or-api-key>
X-Event-ID: event-123
Content-Type: application/json

{
  "sku": "BACKPACK-PRO-01",
  "quantity_delta": -1,
  "order_id": "order-123"
}
```

The platform path segment identifies the event source. The service applies the
delta, records the result, and skips the source platform during fanout. The
order_id or X-Event-ID value is used for replay protection.

This application endpoint still requires its own authentication. Before
connecting a marketplace's native webhook directly, verify the platform
signature and delivery model for the deployment.

## Reconcile a SKU

```http
POST /api/inventory/reconcile?sku=BACKPACK-PRO-01&canonical_stock=48
Authorization: Bearer <token-or-api-key>
```

Reconciliation sets the canonical quantity and records the resulting outbound
updates.

## Audit logs

```http
GET /api/inventory/logs
Authorization: Bearer <token-or-api-key>
```

The endpoint returns the most recent user-scoped synchronization records,
including the source platform, quantity change, new quantity, and fanout
statuses.

## Supported connector names

The connector registry currently includes amazon, shopify, etsy, tiktok,
tiktok_shop, ebay, walmart, temu, and woocommerce. Operation availability and
provider behavior vary by adapter. Configure only the credentials and
permissions required for the selected platform.
