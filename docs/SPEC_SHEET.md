# KopyKat — Comprehensive Technical Specification Sheet

---

## 1. System Architecture

KopyKat is an asynchronous multi-channel e-commerce operating system built on Python 3.11, FastAPI, SQLAlchemy 2.0, and APScheduler. It delivers high-throughput catalog syndication, real-time stock balancing, automated competitor 1-star review mining, SEO blog publishing, and encrypted Bring-Your-Own-Key (BYOK) AI execution.

```
+───────────────────────────────────────────────────────────────────────────+
|                               FASTAPI GATEWAY                             |
|  - Rate Limiter (SlowAPI)     - CORS & Security Middleware (CSP / HSTS)   |
|  - JWT Bearer Auth            - API Key Auth (kk_live_... / SHA-256)      |
+───────────────────────────────────────────────────────────────────────────+
       │                     │                     │                     │
       ▼                     ▼                     ▼                     ▼
+─────────────+       +─────────────+       +─────────────+       +─────────────+
|   CATALOG   |       |  INVENTORY  |       |   REVIEWS   |       |   PRICING   |
|  IMPORTER   |       |  BALANCER   |       |  & UGC HUB  |       |   MONITOR   |
| (CSV / Live |       | (Loop-Free  |       |  (Sentiment |       |    (COGS    |
|   Shopify)  |       |   Fanout)   |       |  Classifier)|       |  Optimizer) |
+─────────────+       +─────────────+       +─────────────+       +─────────────+
       │                     │                     │                     │
       +─────────────────────┼─────────────────────┼─────────────────────+
                             │
                             ▼
+───────────────────────────────────────────────────────────────────────────+
|                           PERSISTENT STORAGE                              |
|  - PostgreSQL / SQLite (SQLAlchemy 2.0 Models)                            |
|  - Fernet Symmetric Credential Vault (INTEGRATION_ENCRYPTION_KEY)         |
+───────────────────────────────────────────────────────────────────────────+
```

---

## 2. Database Schema (11 Models)

| Model Name | Table Name | Key Attributes | Responsibility |
|---|---|---|---|
| **User** | `users` | `id`, `email`, `hashed_password`, `plan`, `generations`, `monthly_limit`, `custom_ai_key_encrypted`, `custom_ai_provider` | User accounts, active plan allocations, and encrypted BYOK credentials. |
| **APIKey** | `api_keys` | `id`, `user_id`, `key_hash` (SHA-256), `key_prefix`, `requests_today` | Programmatic API keys for store webhook authentication. |
| **Subscription** | `subscriptions` | `id`, `user_id`, `stripe_subscription_id`, `plan`, `status`, `current_period_end` | Stripe subscription lifecycle states. |
| **RevenueRecord** | `revenue_records` | `id`, `stripe_payment_id`, `user_id`, `amount_cents`, `plan`, `type`, `status` | Immutable audit log of all financial transactions. |
| **UsageRecord** | `usage_records` | `id`, `user_id`, `endpoint`, `generations_used`, `tokens_used`, `cost_usd` | Per-request generation tracking and token consumption. |
| **UserIntegration** | `user_integrations` | `id`, `user_id`, `platform`, `credentials` (Fernet encrypted), `status` | Saved credentials for Shopify, Amazon, eBay, Walmart, Mailchimp. |
| **InventoryItem** | `inventory_items` | `id`, `user_id`, `sku`, `title`, `total_stock`, `platform_stock` (JSON) | Tracked catalog SKUs and multi-channel stock levels. |
| **InventorySyncLog** | `inventory_sync_logs` | `id`, `user_id`, `sku`, `trigger_platform`, `quantity_change`, `new_quantity`, `fanout_results` (JSON) | Real-time audit trail of order decrements and fanouts. |
| **CustomerReview** | `customer_reviews` | `id`, `user_id`, `customer_name`, `product_name`, `rating`, `review_text`, `sentiment`, `status`, `draft_reply` | Ingested reviews with AI sentiment tagging and resolution replies. |
| **PriceMarginItem** | `price_margin_items` | `id`, `user_id`, `sku`, `product_name`, `cogs_usd`, `selling_price_usd`, `competitor_price_usd`, `current_margin_pct`, `status`, `recommendation` | Unit economics, profit margin badges, and pricing shift suggestions. |
| **BlogPost** | `blog_posts` | `id`, `title`, `slug`, `keyword`, `meta_desc`, `content`, `word_count`, `published` | Published SEO articles targeting high-intent buyer searches. |
| **OpportunityLog** | `opportunity_logs` | `id`, `platform`, `post_id`, `post_url`, `post_title`, `draft_reply`, `alerted` | Social leads discovered across Reddit and online forums. |

---

## 3. Flagship Functional Modules

### Module 1: Competitor 1-Star Review Miner
- **Endpoint:** `POST /api/competitor/mine-reviews`
- **Logic:** Ingests negative customer complaints from competitor listings. Extracts root flaws and generates counter-positioned copy, comparison tables ("Our Build vs. Competitor Flaw"), and direct-response ad angles.

### Module 2: Cross-Platform Inventory Balancer
- **Endpoints:** `POST /api/inventory/webhook/{platform}`, `GET /api/inventory`, `POST /api/inventory/item`, `GET /api/inventory/logs`
- **Logic:** Intercepts order purchase webhooks (e.g. Shopify `orders/create`), atomically decrements total stock in the database, and fans out updates to Amazon, eBay, Walmart, and Temu while skipping the trigger source to prevent infinite sync loops.

### Module 3: Post-Purchase Review & UGC Drip Hub
- **Endpoints:** `POST /api/reviews/drip-templates`, `POST /api/reviews/submit`, `GET /api/reviews`
- **Logic:** Generates 3-step post-delivery customer nurture emails (Day 3 check-in, Day 7 photo/video UGC request with coupon incentive, Day 14 VIP loyalty). Classifies incoming feedback (*Positive*, *Neutral*, *Negative*) and generates merchant resolution replies.

### Module 4: Automated Price & Margin Monitor
- **Endpoints:** `POST /api/pricing/item`, `GET /api/pricing/items`, `DELETE /api/pricing/item/{id}`
- **Logic:** Calculates gross profit margin percentage and profit per unit. Automatically flags dangerous thin margins (< 15%), detects competitor pricing headroom, and recommends defense strategies against undercutting.

### Module 5: Direct 1-Click Shopify Catalog Import
- **Endpoint:** `POST /api/catalog/import-shopify`
- **Logic:** Pulls live products, descriptions, variants, prices, and media directly from Shopify Admin API. Strips HTML descriptions and populates the batch syndication table for instant multi-channel distribution.

---

## 4. Bring Your Own Key (BYOK) Enterprise Engine
- **Target Tier:** `megastore` ($9,639.63 / mo)
- **Endpoints:** `GET /api/user/custom-ai-key`, `POST /api/user/custom-ai-key`, `DELETE /api/user/custom-ai-key`
- **Security:** Keys are encrypted using Fernet symmetric encryption before persistent storage.
- **Quota Bypass:** Megastore users with an active BYOK key bypass monthly generation quotas, enabling unlimited multi-channel campaigns running through KopyKat's infrastructure.

---

## 5. Automated Background Worker Schedules

| Worker | Trigger Interval | Action | Target Table |
|---|---|---|---|
| **SEO Blog Engine** | Mon, Wed, Fri @ 09:00 UTC | Generates 800-word search-intent article targeting e-commerce keywords and publishes to store blog. | `blog_posts` |
| **Email Conversion Drip** | Daily @ 10:00 UTC | Analyzes account age for free-tier users and sends Day 2, Day 4, and Day 7 nurture emails. | `drip_logs` |
| **Social Opportunity Scout** | Every 4 Hours | Scans subreddits (`r/ecommerce`, `r/smallbusiness`, `r/marketing`) for copywriting pain points, drafts AI replies, and notifies owner. | `opportunity_logs` |
| **Counter Reset** | Daily @ Midnight UTC | Resets daily rate counters for API keys. | `api_keys` |

---

## 6. Environment & Security Specifications
- **Python Runtime:** Python 3.11.9
- **Encryption:** AES-128-CBC with HMAC-SHA256 authenticated symmetric encryption via `cryptography.fernet`.
- **Password Hashing:** `bcrypt` with salt rounds >= 12.
- **XSS Protection:** Strict HTML sanitization via `bleach` and safe DOM construction (`textContent` / `createElement`) across frontend.
- **Test Suite:** 33 automated integration and unit tests passing with 100% green status (`pytest -v`).
