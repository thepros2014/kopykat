# KOPYKAT — BUYER-READY ARCHITECTURE & ACQUISITION DOSSIER
CONFIDENTIAL | PREPARED FOR M&A AND TECHNICAL DUE DILIGENCE | VERSION 2.0.0

---

## 1. Executive Summary & Investment Thesis

KopyKat is an autonomous e-commerce syndication, content generation, and revenue operations platform. It bridges the critical gap between high-volume product catalogs and multi-marketplace conversion.

### 1.1 Core Valuation Drivers & Moats
- **Multi-Modal E-Commerce Syndication Engine**: Automatically converts raw product photos and basic titles into five distinct, platform-compliant schemas (Amazon, Shopify, Etsy, TikTok Shop, eBay) in under 30 seconds.
- **Autonomous Connector Engine with SSRF Protection**: Non-blocking asynchronous HTTP client with pre-flight DNS filtering, link-local / loopback blocking, and cryptographic webhook deduplication `(platform, event_id)`.
- **Growth & Marketing Automation**: Built-in automated SEO blog engine, customer review sentiment classifier, Reddit opportunity scout, and post-purchase email sequence generator.
- **High-Margin Unit Economics**: 94.2% gross margin on AI token operations with dual-bucket quota accounting (monthly recurring quota + purchased add-on credits).
- **Institutional Code Quality**: 404 passing automated tests, zero-emoji policy compliance, and clean migration from unmaintained dependencies to `PyJWT[crypto]>=2.9.0` and `cryptography>=44.0.1`.

---

## 2. Financial Metrics & Unit Economics

| Metric | Current Value | Benchmark Context |
|:---|:---|:---|
| **Monthly Recurring Revenue (MRR)** | **$3,450.00** | +18.5% MoM net growth |
| **Annualized Run Rate (ARR)** | **$41,400.00** | High recurring predictability |
| **Active Paid Customers** | **42 Merchants** | Distributed across Boutique, Standard, Megastore |
| **Average Revenue Per User (ARPU)** | **$82.14 / mo** | Supported by recurring Add-On subscriptions |
| **Customer Lifetime Value (LTV)** | **$1,850.00** | High retention due to multi-store lock-in |
| **Customer Acquisition Cost (CAC)** | **$42.00** | Driven primarily by organic SEO and viral tool loops |
| **LTV / CAC Ratio** | **44.0x** | Exceptional capital efficiency |
| **Net Revenue Retention (NRR)** | **118.4%** | Positive expansion revenue via Add-Ons |
| **Gross Margin on Generation** | **94.2%** | Minimal compute overhead per campaign |

---

## 3. Comprehensive System Architecture

```
+-----------------------------------------------------------------------------------------------+
|                                    KOPYKAT ARCHITECTURE TOPOLOGY                              |
|                                                                                               |
|  [Merchant Admin / API]  --->  [HTTPS / TLS 1.3]  --->  [FastAPI ASGI Gateway]               |
|                                                               |                               |
|        +------------------------------------------------------+-----------------------+       |
|        |                                                      |                       |       |
|        v                                                      v                       v       |
|  [Auth & Tenant Guard]                                  [SlowAPI Limiter]       [SSRF Shield] |
|  - PyJWT Bearer Auth                                    - Leaky Bucket Token    - DNS Pre-Res |
|  - SHA-256 Key Hashes                                   - IP Tier Throttling    - Safe Async  |
|                                                                                               |
|        +------------------------------------------------------------------------------+       |
|        |                                CORE PIPELINES                                |       |
|        v                                                      v                       v       |
|  [Multi-Modal Vision Engine]                            [Connector Engine]      [Growth Engine]
|  - Amazon (5 Bullets, Terms)                            - Shopify / Amazon      - SEO Blog Gen|
|  - Shopify (HTML, Meta)                                 - TikTok / Etsy / eBay  - Review Miner|
|  - Etsy (13 Search Tags)                                - Webhook Deduplication - Reddit Scout|
|  - TikTok Shop (30s Hooks)                              - Row-Level Locking     - Drip Emails |
|  - eBay (80-Char Limits)                                - Drift Reconciliation  - Margin Guard|
|                                                                                               |
|        +------------------------------------------------------------------------------+       |
|        |                               DATA PERSISTENCE                               |       |
|        v                                                                              v       |
|  [PostgreSQL / SQLite Database Engine]                              [Fernet Credential Vault] |
|  - Isolated Multi-Tenant Relational Tables                          - Encrypted API Keys      |
+-----------------------------------------------------------------------------------------------+
```

---

## 4. Proprietary Intellectual Property & Assets

1. **Deterministic Fallback Schemas**: High-reliability templating and JSON extraction algorithms that prevent downstream pipeline failure even during AI provider outages.
2. **SafeAsyncHTTPClient Network Shield**: Zero-trust outbound request validator preventing server-side request forgery, DNS rebinding attacks, and payload exhaustion.
3. **Dual-Bucket Quota Ledger**: Transaction-isolated financial accounting preventing race conditions, balance underflows, and phantom consumption.
4. **Zero-Emoji Clean Code Policy**: Continuous integration enforcement ensuring strictly professional output formats across all channels.

---

## 5. Technical Due Diligence Checklist

- [x] **Repository Cleanliness**: 0 syntax errors (`flake8 server --count --select=E9,F63,F7,F82`).
- [x] **Test Coverage**: 404 / 404 tests passing across unit, boundary, multi-channel enterprise, and Tier 5 adversarial stress tests.
- [x] **Vulnerability Remediation**: All 23 Dependabot security alerts patched and closed.
- [x] **Database Migration & Concurrency**: Pessimistic row locking with unique compound webhook constraints.
- [x] **Frontend Architecture**: Dual distribution featuring lightweight semantic HTML5/CSS3 client and modern React 18 / TypeScript SPA.
- [x] **OpenAPI Specification**: Interactive Swagger docs available at `/api/docs` and `/api/openapi.json`.
