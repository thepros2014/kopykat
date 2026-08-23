# Comprehensive Technical Analysis: Autonomous Platform Connectors (Milestone 2)

**Author:** Explorer 2 (Milestone 2 - Autonomous Connectors, Real-Time Sync & Async SSRF Defense)  
**Date:** 2026-08-23  
**Status:** Completed  
**Target Modules:** `server/integrations.py`, `server/connector_engine.py`, `server/inventory.py`, `server/database.py`, `tests/test_connectors.py`

---

## 1. Executive Summary & Problem Scope

KopyKat Milestone 2 requires expanding the platform's multi-channel integration layer into an enterprise-grade, autonomous connector suite supporting the top 5 e-commerce marketplaces: **Amazon**, **Shopify**, **Etsy**, **TikTok Shop**, and **eBay**.

### Key Architectural Objectives
1. **Universal Protocol Contract:** Establish a standardized `PlatformConnector` Protocol defining `fetch_catalog`, `push_product`, `update_stock`, and `verify_webhook`.
2. **Autonomous Marketplace Adapters:** Implement concrete async connectors for Amazon (SP-API), Shopify (Admin API), Etsy (v3 API), TikTok Shop (Open API), and eBay (Inventory API).
3. **Async Non-Blocking Execution with Strict SSRF Defense:** Integrate connectors with `SafeAsyncHTTPClient` to eliminate TOCTOU DNS rebinding, block private/loopback IP routing, enforce 2MB streaming payload caps, and eliminate thread-blocking I/O.
4. **Resilient Error & Rate Limit Handling:** Implement hierarchical exception handling (`ConnectorAuthError`, `ConnectorRateLimitError`, `ConnectorNetworkError`, `ConnectorValidationError`) and exponential backoff with jitter on HTTP 429 / transient 5xx errors.
5. **Idempotent Webhook Processing & Cryptographic Signatures:** Implement platform-specific signature verification (HMAC-SHA256, Base64/Hex digest) and tie into the `(platform, event_id)` idempotency ledger.
6. **Encrypted Credential Security:** Decrypt credentials on-demand using Fernet (`decrypt_credentials`) without persisting decrypted keys in memory or logs.
7. **Zero-Emoji Policy & Flake8 Compliance:** 100% adherence to the zero-emoji invariant and flake8 linting standards (line length <= 120 chars, strict types).

---

## 2. Current Codebase State vs Target Architecture

### 2.1 Existing Integrations (`server/integrations.py`)
- **Current State:** Contains legacy synchronous push functions (`push_to_wordpress`, `push_to_mailchimp`, `push_to_hubspot`, `push_to_shopify`, `push_to_webflow`) using synchronous `requests.post()`.
- **Marketplace Stubs:** `push_to_amazon`, `push_to_ebay`, `push_to_walmart`, and `push_to_temu` raise `NotImplementedError` via `_unsupported_marketplace()`.
- **Missing Interfaces:** No standardized `PlatformConnector` protocol exists. Connectors lack `fetch_catalog`, `update_stock`, and `verify_webhook` methods.
- **SSRF Limitation:** `_validate_external_url()` validates IP addresses prior to request execution, but downstream `requests` executes a secondary DNS lookup, creating a TOCTOU DNS rebinding vulnerability.

### 2.2 Target Architecture (`server/integrations.py`)
```
+-------------------------------------------------------------------------+
|                        PlatformConnector Protocol                       |
|  + platform_name: str                                                   |
|  + fetch_catalog(credentials: dict, limit: int = 50) -> list[dict]      |
|  + push_product(credentials: dict, product_data: dict) -> dict          |
|  + update_stock(credentials: dict, sku: str, quantity: int) -> dict     |
|  + verify_webhook(headers: dict, raw_payload: bytes, secret: str) -> bool|
+-------------------------------------------------------------------------+
       ^                   ^                ^            ^            ^
       |                   |                |            |            |
+---------------+ +------------------+ +----------+ +----------+ +----------+
|AmazonConnector| | ShopifyConnector | |EtsyConnec| |TikTokConn| |EBayConnec|
| (Amazon SPAPI)| | (Admin REST/GQL) | |(v3 OAuth)| |(Open API)| |(Inv. API)|
+---------------+ +------------------+ +----------+ +----------+ +----------+
       |                   |                |            |            |
       +-------------------+----------------+------------+------------+
                                   |
                       +-----------------------+
                       |  SafeAsyncHTTPClient  |  (SSRF / Socket Pinning / 2MB Cap)
                       +-----------------------+
```

---

## 3. Standardized `PlatformConnector` Interface Specification

```python
from __future__ import annotations
from typing import Protocol, Any, Optional

class PlatformConnector(Protocol):
    """Universal contract for marketplace and e-commerce platform connectors."""
    platform_name: str

    async def fetch_catalog(self, credentials: dict[str, Any], limit: int = 50) -> list[dict[str, Any]]:
        """
        Fetches active product listings from the platform.
        Returns a normalized list of dictionaries containing:
        - sku (str): Merchant SKU
        - title (str): Product title
        - description (str): Clean plain-text description
        - price (float): Unit selling price
        - quantity (int): Available inventory count
        - image_url (str): Primary product image URL
        - raw_id (str): Platform-specific listing ID (e.g. ASIN, listing_id)
        """
        ...

    async def push_product(self, credentials: dict[str, Any], product_data: dict[str, Any]) -> dict[str, Any]:
        """
        Creates or updates a product listing on the remote platform.
        Returns a dictionary containing:
        - success (bool): True if created/accepted
        - sku (str): Product SKU
        - listing_id (str): Platform listing/submission identifier
        - status (str): Listing status (e.g. 'active', 'draft', 'submitted')
        - raw_response (dict): Upstream platform response details
        """
        ...

    async def update_stock(self, credentials: dict[str, Any], sku: str, quantity: int) -> dict[str, Any]:
        """
        Updates stock quantity for a single SKU.
        Returns a dictionary containing:
        - success (bool): True if stock update was accepted
        - sku (str): Product SKU
        - quantity (int): New stock level applied
        - platform (str): Target platform name
        """
        ...

    def verify_webhook(self, headers: dict[str, str], raw_payload: bytes, secret: str) -> bool:
        """
        Cryptographically validates incoming webhook signatures using constant-time comparison.
        Returns True if signature is valid, False otherwise.
        """
        ...
```

---

## 4. Deep-Dive Marketplace Connector Specifications

### 4.1 Amazon Connector (`AmazonConnector`)
- **Platform Name:** `"amazon"`
- **Protocol:** SP-API (Selling Partner API - Listings Items & Catalog Items APIs)
- **Credential Schema:**
  ```python
  {
      "seller_id": str,          # Selling partner merchant ID
      "access_token": str,       # LWA (Login with Amazon) access token
      "refresh_token": str,      # Optional LWA refresh token
      "client_id": str,          # Optional LWA client ID
      "client_secret": str,      # Optional LWA client secret
      "marketplace_id": str,     # Default: "ATVPDKIKX0DER" (Amazon US)
      "region": str,             # Default: "na" (North America)
      "endpoint_url": str        # Default: "https://sellingpartnerapi-na.amazon.com"
  }
  ```
- **Operations:**
  1. `fetch_catalog`: Queries `GET /catalog/2022-04-01/items?marketplaceIds={marketplace_id}&pageSize={limit}`. Extracts ASIN, title, price, and media links.
  2. `push_product`: Sends `PUT /listings/2021-08-01/items/{seller_id}/{sku}?marketplaceIds={marketplace_id}` with JSON schema listing payload including `item_name`, `bullet_point`, `generic_keyword`, and `purchasable_offer`.
  3. `update_stock`: Sends `PATCH /listings/2021-08-01/items/{seller_id}/{sku}?marketplaceIds={marketplace_id}` with JSON Patch `[{"op": "replace", "path": "/attributes/fulfillment_availability", "value": [{"fulfillment_channel_code": "DEFAULT", "quantity": quantity}]}]`.
  4. `verify_webhook`: Validates `x-amz-signature` / `x-amzn-signature` using HMAC-SHA256 hex digest comparison (`hmac.compare_digest`).

### 4.2 Shopify Connector (`ShopifyConnector`)
- **Platform Name:** `"shopify"`
- **Protocol:** Shopify Admin REST API (2024-01) & GraphQL Admin API
- **Credential Schema:**
  ```python
  {
      "shop_url": str,           # Store domain e.g. "brand-store.myshopify.com"
      "access_token": str,       # Admin API Access Token (shpat_...)
      "location_id": str         # Optional default fulfillment location ID
  }
  ```
- **Operations:**
  1. `fetch_catalog`: Queries `GET https://{shop_url}/admin/api/2024-01/products.json?limit={limit}`. Sanitizes HTML descriptions and extracts variants, prices, inventory, and images.
  2. `push_product`: Sends `POST https://{shop_url}/admin/api/2024-01/products.json` with `{"product": {"title": title, "body_html": html_desc, "variants": [{"sku": sku, "price": price, "inventory_quantity": qty}], "images": [{"src": url}]}}`.
  3. `update_stock`: Sends `POST https://{shop_url}/admin/api/2024-01/inventory_levels/set.json` with `{"location_id": loc_id, "inventory_item_id": inv_id, "available": quantity}` or variant update endpoint.
  4. `verify_webhook`: Validates `X-Shopify-Hmac-Sha256` header by calculating Base64-encoded HMAC-SHA256 digest of `raw_payload` with shared webhook secret.

### 4.3 Etsy Connector (`EtsyConnector`)
- **Platform Name:** `"etsy"`
- **Protocol:** Etsy Open API v3 (REST OAuth 2.0)
- **Credential Schema:**
  ```python
  {
      "keystring": str,          # Etsy App API Keystring / Client ID
      "access_token": str,       # OAuth 2.0 Bearer token
      "shop_id": str,            # Merchant Shop ID
      "endpoint_url": str        # Default: "https://openapi.etsy.com/v3"
  }
  ```
- **Operations:**
  1. `fetch_catalog`: Queries `GET /v3/application/shops/{shop_id}/listings/active?limit={limit}&includes=Images,Inventory`. Normalizes pricing (dividing `amount` by `divisor`), tags, and stock counts.
  2. `push_product`: Sends `POST /v3/application/shops/{shop_id}/listings` with `{"title": title[:140], "description": desc, "price": price, "quantity": qty, "tags": tags[:13], "who_made": "i_did", "is_supply": false, "when_made": "2020_2026", "taxonomy_id": 1}`.
  3. `update_stock`: Sends `PUT /v3/application/listings/{listing_id}/inventory` with `{"products": [{"sku": sku, "offerings": [{"price": price, "quantity": quantity, "is_enabled": 1}]}]}`.
  4. `verify_webhook`: Validates `X-Etsy-Signature` / `X-Etsy-Hmac-Sha256` hex digest using constant-time comparison.

### 4.4 TikTok Shop Connector (`TikTokShopConnector`)
- **Platform Name:** `"tiktok"` (aliases: `"tiktok_shop"`)
- **Protocol:** TikTok Shop Open API (2023-09)
- **Credential Schema:**
  ```python
  {
      "app_key": str,            # Partner App Key
      "app_secret": str,         # Partner App Secret for request signing
      "access_token": str,       # Seller access token
      "shop_cipher": str,        # Shop Cipher identifier
      "endpoint_url": str        # Default: "https://open-api.tiktokglobalshop.com"
  }
  ```
- **Operations:**
  1. `fetch_catalog`: Sends `POST /product/202309/products/search?app_key={app_key}&shop_cipher={shop_cipher}` with `{"page_size": limit, "page_number": 1}`. Extracts SKU details, prices, and warehouse inventory.
  2. `push_product`: Sends `POST /product/202309/products?app_key={app_key}&shop_cipher={shop_cipher}` with title, category, description, and SKU price/quantity matrices.
  3. `update_stock`: Sends `POST /product/202309/inventory/update?app_key={app_key}&shop_cipher={shop_cipher}` with `{"skus": [{"seller_sku": sku, "inventory": [{"quantity": quantity}]}]}`.
  4. `verify_webhook`: Validates `Authorization` / `X-Tts-Signature` header against HMAC-SHA256 signature generated with `app_secret`.

### 4.5 eBay Connector (`EBayConnector`)
- **Platform Name:** `"ebay"`
- **Protocol:** eBay REST Inventory API & Fulfillment API
- **Credential Schema:**
  ```python
  {
      "access_token": str,       # User OAuth access token
      "marketplace_id": str,     # Default: "EBAY_US"
      "endpoint_url": str        # Default: "https://api.ebay.com/sell/inventory/v1"
  }
  ```
- **Operations:**
  1. `fetch_catalog`: Queries `GET /inventory_item?limit={limit}` with header `X-EBAY-C-MARKETPLACE-ID: {marketplace_id}`. Parses title, description, aspect specifics, and ship-to-location availability.
  2. `push_product`: Sends `PUT /inventory_item/{sku}` with product specifics, condition (`NEW`), and available quantity.
  3. `update_stock`: Sends `POST /bulk_update_price_quantity` or `PUT /inventory_item/{sku}` with updated `shipToLocationAvailability.quantity`.
  4. `verify_webhook`: Validates `X-EBAY-SIGNATURE` header against HMAC-SHA256 signature using constant-time comparison.

---

## 5. Security & Safe Async HTTP Integration

### 5.1 Defense against SSRF & DNS Rebinding
Customer-provided endpoints (such as custom Shopify domains or webhook destinations) must route strictly through `SafeAsyncHTTPClient`:
- **Pre-Resolution:** Hostnames are resolved once against system DNS.
- **Range Verification:** Addresses within RFC 1918 (private), RFC 3927 (link-local `169.254.0.0/16`), loopback (`127.0.0.0/8`, `::1`), multicast (`224.0.0.0/4`), carrier-grade NAT (`100.64.0.0/10`), and reserved networks are immediately rejected.
- **Socket Pinning:** Outbound TCP/TLS sockets connect directly to the pre-verified IP address while preserving the original `Host` and SNI headers to prevent TOCTOU DNS rebinding.
- **Redirect Denial:** `allow_redirects=False` prevents attackers from bouncing requests from a public URL to an internal network interface.
- **Stream Cap:** Max response byte stream is strictly capped at `2,000,000` bytes (2 MB) to prevent denial-of-service memory exhaustion.

### 5.2 Decrypted Credential Lifecycle
- Credentials in `UserIntegration` table are stored Fernet-encrypted (`encrypt_credentials(json.dumps(credentials))`).
- The connector execution layer decrypts credentials in-memory at execution time via `decrypt_credentials(integ.credentials)`.
- Decrypted keys are never logged, never returned in API responses, and never stored in connector specs or audit tables.

---

## 6. Error Handling & Rate Limiting Strategy

### 6.1 Exception Hierarchy
```python
class ConnectorError(Exception):
    """Base exception for all connector runtime errors."""
    pass

class ConnectorAuthError(ConnectorError):
    """Raised on 401/403 or invalid authentication credentials."""
    pass

class ConnectorRateLimitError(ConnectorError):
    """Raised on 429 Too Many Requests."""
    def __init__(self, message: str, retry_after_seconds: float = 60.0):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds

class ConnectorNetworkError(ConnectorError):
    """Raised on timeouts, connection drops, or upstream 5xx errors."""
    pass

class ConnectorValidationError(ConnectorError):
    """Raised on 400/422 payload or schema validation errors."""
    pass
```

### 6.2 Retry Backoff Architecture
When communicating with remote marketplace APIs:
- Status 429 triggers `retry-after` header extraction.
- Transient errors (HTTP 429, 502, 503, 504) trigger exponential backoff:
  - Attempt 1: 0.5s + jitter
  - Attempt 2: 1.0s + jitter
  - Attempt 3: 2.0s + jitter
- Fatal errors (400 Bad Request, 401 Unauthorized, 404 Not Found) fail fast without retrying.

---

## 7. Registry & Factory Implementation Design

```python
CONNECTOR_REGISTRY: dict[str, PlatformConnector] = {
    "amazon": AmazonConnector(),
    "shopify": ShopifyConnector(),
    "etsy": EtsyConnector(),
    "tiktok": TikTokShopConnector(),
    "tiktok_shop": TikTokShopConnector(),
    "ebay": EBayConnector(),
}

def get_connector(platform: str) -> PlatformConnector:
    """Returns the registered PlatformConnector instance for a given platform name."""
    normalized = platform.strip().lower()
    if normalized not in CONNECTOR_REGISTRY:
        raise ValueError(
            f"Unsupported connector platform '{platform}'. "
            f"Supported platforms: {sorted(list(CONNECTOR_REGISTRY.keys()))}"
        )
    return CONNECTOR_REGISTRY[normalized]
```

---

## 8. Verification & Test Suite Blueprint

The test suite in `tests/test_connectors.py` will verify:
1. **Contract Conformance:** All 5 connectors satisfy `isinstance(connector, PlatformConnector)` or adhere to `Protocol` typing.
2. **Catalog Fetching:** Mocked HTTP responses return normalized catalog listings across all platforms.
3. **Product Publishing:** Mocked HTTP requests assert proper payload formatting, title truncations, and status returns.
4. **Stock Updating:** Mocked inventory endpoints verify correct SKU and quantity updates.
5. **Webhook Signature Verification:** Positive and negative test cases verifying HMAC-SHA256 (Shopify, Amazon, Etsy, TikTok, eBay) signatures.
6. **Error Resilience:** Assert `ConnectorAuthError` on 401, `ConnectorRateLimitError` on 429, and `ConnectorNetworkError` on 500.
7. **Zero-Emoji Check:** `pytest tests/test_no_emojis.py` passes 100%.
8. **Flake8 Compliance:** `flake8 server --count --select=E9,F63,F7,F82` returns 0 errors.

---
