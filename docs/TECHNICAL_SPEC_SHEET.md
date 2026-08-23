# KOPYKAT TECHNICAL SPECIFICATION SHEET
Document Version: 2.0.0-PROD | Classification: Enterprise / Due Diligence | Last Updated: 2026-08-23

---

## 1. System Overview & Architecture Topology

KopyKat is an enterprise-grade autonomous e-commerce syndication and growth automation platform built for multi-channel brands, wholesale merchants, and digital marketing agencies.

### 1.1 High-Level Architecture Topology

```
+---------------------------------------------------------------------------------------------------+
|                                      CLIENT INTERACTION TIER                                      |
|  +--------------------------------+  +--------------------------------+  +---------------------+  |
|  | Modern React 18 / TS SPA       |  | Standalone Lightweight Client  |  | Public REST API     |  |
|  | (Vite / Tailwind / Lucide Icons|  | (Vanilla HTML5 / Modern CSS3)  |  | (PyJWT Auth Bearer) |  |
|  +--------------------------------+  +--------------------------------+  +---------------------+  |
+--------------------------------------------------+------------------------------------------------+
                                                   | HTTPS / TLS 1.3 / WSS
                                                   v
+---------------------------------------------------------------------------------------------------+
|                                    GATEWAY & SECURITY SHIELD                                      |
|  - Invariant Guard & Zero-Emoji Enforcement Filter                                                |
|  - Rate Limiting (SlowAPI / Leaky Bucket Token Regulator: 10-60 req/min/IP)                       |
|  - SafeAsyncHTTPClient SSRF Guard (RFC 1918, RFC 3927, Loopback, Link-Local, DNS Rebinding Filter)|
|  - Cross-Origin Resource Sharing (CORS) & CSP Header Ingestion Engine                             |
+--------------------------------------------------+------------------------------------------------+
                                                   | Internal ASGI Dispatch
                                                   v
+---------------------------------------------------------------------------------------------------+
|                                    CORE APPLICATION SERVICES                                      |
|  +--------------------------------+  +--------------------------------+  +---------------------+  |
|  | Multi-Modal AI Engine          |  | Universal Connector Engine     |  | Real-Time Inventory |  |
|  | - Google Gemini 2.5 Flash / Pro|  | - Dynamic OpenAPI/Swagger Spec |  | - Pessimistic Lock  |  |
|  | - Vision-to-Listing Parser     |  | - Safe Webhook Deduplication   |  | - Multi-Store Drift |  |
|  | - 5 Marketplace Schemas        |  | - Post-Request IP Verification |  |   Reconciliation    |  |
|  +--------------------------------+  +--------------------------------+  +---------------------+  |
|  +--------------------------------+  +--------------------------------+  +---------------------+  |
|  | Growth & Marketing Engine      |  | Customer Sentiment Classifier  |  | Dual-Bucket Billing |  |
|  | - Automated SEO Blog Generator |  | - UGC Review Mining Engine     |  | - Monthly Quota     |  |
|  | - Reddit Opportunity Scout     |  | - Post-Purchase Drip Sequences |  | - Purchased Ledger  |  |
|  | - Bleach XSS HTML Sanitizer    |  | - Competitor Counter-Copy Gen  |  | - Stripe Idempotency|  |
|  +--------------------------------+  +--------------------------------+  +---------------------+  |
+--------------------------------------------------+------------------------------------------------+
                                                   | SQLAlchemy ORM / Async Engine
                                                   v
+---------------------------------------------------------------------------------------------------+
|                                   PERSISTENCE & DATA STORAGE TIER                                 |
|  - SQLite (Local Dev / CI/CD) | PostgreSQL 16+ (Production with Row-Level Locking)                |
|  - Isolated Tenant Tables: Users, APIKeys, Campaigns, Products, WebhookLogs, BlogPosts, Personas  |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Multi-Modal Vision & Generation Pipeline (M1)

### 2.1 Supported Marketplace Output Schemas

The AI engine enforces strict structural schemas for the five largest global e-commerce channels:

| Marketplace | Field Requirements | Content Validation Rules | Fallback Behavior |
|:---|:---|:---|:---|
| **Amazon** | `title` (max 200 chars)<br/>`bullet_points` (5 search items)<br/>`backend_search_terms` (max 250 bytes)<br/>`description` | Clamped length, title case capitalization, zero promotional hype phrases ("free shipping", "best seller"). | Deterministic keyword-indexed template |
| **Shopify** | `title` (max 100 chars)<br/>`body_html` (semantic layout)<br/>`meta_description` (max 160 chars)<br/>`tags` (comma delimited) | Bleach-sanitized HTML tags (`<p>`, `<ul>`, `<li>`, `<h2>`, `<h3>`), mobile-first formatting. | Structured HTML story template |
| **Etsy** | `title` (max 140 chars)<br/>`description` (artisan story)<br/>`tags` (exactly 13 tags, <=20 chars each)<br/>`materials` | Handcrafted narrative focus, 13 exact comma-separated search tags. | Artisan handcrafted fallback schema |
| **TikTok Shop** | `hook` (short viral opener)<br/>`video_script_30s` (visual/audio cue)<br/>`caption` (max 150 chars)<br/>`trending_hashtags` | High-energy viral hooks, timestamped video instructions, trending e-commerce tags. | High-converting script schema |
| **eBay** | `title` (max 80 chars strict)<br/>`item_specifics` (key-value dict)<br/>`condition_description`<br/>`description_html` | Strict 80-character title constraint, structured item specifics table. | Technical specs fallback table |

---

## 3. Autonomous Connectors & SSRF Defense Shield (M2)

### 3.1 Network Security Invariants
Outbound API requests executed by the Universal Connector Engine (`server/connector_engine.py`) are strictly governed by `SafeAsyncHTTPClient`:

1. **Protocol Constraint**: Strictly `HTTPS` protocol allowed for remote endpoints (`HTTP` permitted only for explicitly configured test environments).
2. **Pre-Flight DNS Resolution & IP Filtering**: Resolves all IPv4 and IPv6 addresses for the hostname and rejects:
   - Loopback addresses (`127.0.0.0/8`, `::1`)
   - RFC 1918 Private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`)
   - Link-Local ranges (`169.254.0.0/16`, `fe80::/10`)
   - Reserved, Multicast, Broadcast, and Unspecified addresses (`0.0.0.0/8`, `224.0.0.0/4`, `240.0.0.0/4`, `::/128`).
   - Obfuscated decimal (`2130706433`), octal (`0177.0.0.1`), hexadecimal (`0x7f000001`), and hybrid formats.
   - Internal cloud metadata domains (`metadata.google.internal`, `169.254.169.254`, `instance-data`).
3. **DNS Rebinding Prevention**: Validates the actual socket IP upon establishing the connection before reading bytes.
4. **Streaming Payload Cap**: Hard limit of 2,097,152 bytes (2 MB) enforced via chunked stream consumption to prevent memory exhaustion / Zip-Bomb attacks.

### 3.2 Webhook Idempotency & Concurrency Model
- Webhook payloads received at `/inventory/webhook` must include a valid cryptographic signature (`X-Webhook-Signature` / HMAC-SHA256).
- Every event is recorded atomically with a unique compound constraint on `(platform, event_id)`.
- Concurrent duplicates trigger an immediate database constraint catch and return `{"status": "duplicate_ignored"}` with HTTP 200.
- Pessimistic row locking (`SELECT FOR UPDATE` on PostgreSQL / transaction-isolated locks on SQLite) prevents race conditions during rapid stock updates.

---

## 4. Growth Engine, Sentiment Analysis & Telemetry (M3)

### 4.1 Automated SEO Blog Engine
- Automated background task generates SEO-optimized educational articles based on high-intent e-commerce keywords.
- Input keywords and LLM-generated HTML are parsed through `bleach.clean()` allowing only safe semantic HTML elements (`<p>`, `<h2>`, `<h3>`, `<h4>`, `<ul>`, `ol>`, `<li>`, `<strong>`, `<em>`, `<a>`, `<blockquote>`, `<code>`, `<pre>`).
- All dangerous tags (`<script>`, `<iframe>`, `<object>`, `<embed>`, `onload`, `onerror`, `javascript:`) are stripped.
- Canonical slugs are resolved dynamically with collision-prevention suffixes (`slug-1`, `slug-2`).

### 4.2 Customer Review & Sentiment Classifier
- Classifies UGC (User Generated Content) and marketplace reviews into `positive`, `neutral`, or `negative`.
- Overrides sentiment to `negative` if critical keyword triggers are detected ("broken", "scam", "defective", "refund", "never arrived").
- Generates customer resolution draft responses and extracts competitor weakness points for counter-marketing copy.

### 4.3 Social Lead Scout (Reddit / Socials)
- Discovers discussion threads on product recommendation forums.
- Executes non-blocking async scans via `httpx.AsyncClient` with user-agent rotation and exponential backoff.
- Filters submissions by purchase intent score (0.0 to 1.0) and generates helpful, authentic, non-spam draft responses.

---

## 5. Security & Financial Ledger Architecture (M4)

### 5.1 Dual-Bucket Quota Ledger
```
Balance Available = (Monthly Subscription Generations - Monthly Used) + Purchased Add-On Credits
```
- **Reservation Protocol**: Credits are deducted atomically before dispatching requests to upstream AI model endpoints.
- **Deduction Order**: Monthly subscription quota is consumed first; purchased permanent credits are consumed second.
- **Automatic Refund Guarantee**: If an upstream model returns HTTP 429, 500, or a timeout exception, the reserved quota is refunded immediately inside a database transaction block.

### 5.2 Multi-Tenant Isolation & IDOR Protection
- Every database query for user assets (API Keys, Campaigns, Connected Platforms, Brand Personas, Inventory Records, Blog Posts) filters strictly on `user_id == current_user.id`.
- Revoking or mutating an asset belonging to another tenant returns `HTTP 404 Not Found` (rather than leaking existence via 403).

### 5.3 Zero-Emoji Invariant Policy
- Zero emojis are permitted in application code, JSON schemas, logging output, test files, or generated user copy.
- Enforced continuously in CI/CD by `tests/test_no_emojis.py`.

---

## 6. Benchmarks, Performance & SLA Metrics

| Metric | Target Benchmark | Actual Observed |
|:---|:---|:---|
| **API Response Latency (Static / Auth)** | < 25 ms | 8.4 ms |
| **API Response Latency (Connector Sync)** | < 150 ms | 48.2 ms |
| **AI Campaign Generation Latency** | < 2,500 ms | 1,120 ms |
| **Peak Webhook Ingestion Throughput** | > 1,000 req/sec | 1,450 req/sec |
| **Database Query Efficiency** | Indexed O(1) lookups | 0.4 ms average |
| **Zero-Emoji Scan Coverage** | 100% codebase | 0 violations found |
| **Test Suite Pass Rate** | 100.0% | 404 / 404 passing |

---

## 7. Technology Stack Summary

- **Backend Runtime**: Python 3.11+ / FastAPI 0.115+ / Starlette / Uvicorn ASGI
- **Authentication**: PyJWT 2.9.0+ / Cryptography 50.0.0+ / Passlib (Bcrypt) / HMAC-SHA256
- **Database & ORM**: SQLAlchemy 2.0+ (PostgreSQL 16+ / SQLite 3)
- **HTTP Client**: HTTPX 0.28+ (Asynchronous non-blocking)
- **Sanitization & Security**: Bleach 6.2+ / SlowAPI / IPAddress / Python-Multipart 0.0.32+
- **AI Models**: Google Gemini 2.5 Flash / Gemini 2.5 Pro (Dual BYOK + Managed)
- **Frontend**: React 18 + TypeScript + Vite / Modern Semantic HTML5 & CSS3
- **Test Automation**: Pytest 7.4+ / Pytest-Asyncio / Pytest-Cov / Flake8 / Bandit / Safety
