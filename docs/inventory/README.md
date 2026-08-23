# KopyKat — Cross-Platform Inventory & Stock Balancer

The Cross-Platform Inventory Balancer synchronizes stock counts in real time across multiple marketplace storefronts (Shopify, Amazon, eBay, Walmart, Temu) upon order purchase events to prevent overselling.

---

## 1. Loop-Free Fanout Mechanism

When an order event occurs on a connected store (e.g. Shopify):
1. **Webhook Ingestion:** Shopify sends `orders/create` webhook payload to `POST /api/inventory/webhook/shopify`.
2. **Atomic Stock Decrement:** Total stock count is atomically decremented in `inventory_items` table.
3. **Loop Prevention:** The trigger platform (`shopify`) is labeled as `source_event` and skipped from outbound calls.
4. **Marketplace Fanout:** The balancer dispatches stock update payloads in parallel to all other active connected channels (`amazon`, `ebay`, `walmart`).
5. **Audit Logging:** An immutable record is created in `inventory_sync_logs` tracking the delta, new quantity, and status.

---

## 2. Supported Platforms

- **Shopify:** Admin REST & GraphQL Inventory Levels API
- **Amazon:** Selling Partner API (SP-API) Inventory Feed
- **eBay:** Inventory API `bulkUpdatePriceQuantity`
- **Walmart:** Marketplace Inventory API
- **Temu:** Direct Catalog Sync Endpoint
- **WooCommerce:** REST API v3 Stock Endpoints
