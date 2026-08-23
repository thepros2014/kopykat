# KOPYKAT CHANGELOG
All notable changes to the KopyKat platform are documented in this file in adherence with [Semantic Versioning (SemVer 2.0.0)](https://semver.org/).

---

## [2.0.0] - 2026-08-23 (Enterprise Multi-Modal & Growth Release)

### Added
- **Multi-Modal AI Pipeline (M1)**: Automated vision and image-to-listing generation for Amazon, Shopify, Etsy, TikTok Shop, and eBay with deterministic schema enforcement and clamped length limits.
- **Autonomous Connector Engine & SSRF Shield (M2)**: `SafeAsyncHTTPClient` with pre-flight DNS filtering, private/loopback/link-local/rebound IP blocking, 2 MB payload streaming limits, and cryptographic webhook deduplication `(platform, event_id)`.
- **Growth Engine & Sentiment Telemetry (M3)**: Automated SEO blog generator with `bleach` XSS sanitization, customer review sentiment classifier, Reddit opportunity scout, and real-time MRR analytics.
- **Security Invariant Ledger & Multi-Tenant IDOR Guard (M4)**: Dual-bucket quota balance accounting (monthly + purchased), pessimistic row locking, Stripe HTTP 503 gateway fallback, and strict zero-emoji enforcement.
- **Testing Expansion**: Automated test suite expanded to 404 passing tests spanning unit, integration, boundary, multi-channel enterprise scenarios, and Tier 5 adversarial stress tests.
- **Modern React + TypeScript Architecture**: Production-ready React 18 + Vite + TypeScript application workspace under `frontend/react-app/`.
- **Acquisition Assets**: Comprehensive `docs/TECHNICAL_SPEC_SHEET.md`, `docs/BUYER_READY_ARCHITECTURE.md`, and compiled `docs/BUYER_READY_ARCHITECTURE.pdf`.

### Changed
- Migrated token verification in `server/auth.py` from unmaintained `python-jose` to `PyJWT[crypto]>=2.9.0`.
- Upgraded `cryptography>=44.0.1` and `python-multipart>=0.0.20`, resolving all 23 Dependabot security advisories.
- Redesigned landing page (`frontend/index.html`) with plain English e-commerce benefits, interactive tabbed demo box, comparison chart, and ROI calculator.

---

## [1.3.0] - 2026-08-20 (Universal Connector & Inventory Balancer)

### Added
- Dynamic OpenAPI / Swagger specification ingestion for third-party marketplace discovery.
- Cross-platform inventory balance reconciliation and drift correction.
- Price and profit margin monitor factoring in marketplace transaction fees and shipping overhead.

### Fixed
- Fixed race condition in concurrent webhook event processing via compound unique constraint.
- Fixed BYOK token calculation and API key prefix hashing.

---

## [1.2.0] - 2026-08-15 (Growth & UGC Review Suite)

### Added
- Post-purchase automated drip email campaign generator.
- Competitor review miner for automated counter-copy generation.
- Brand persona tone cloner supporting 8 distinct voice profiles.

---

## [1.1.0] - 2026-08-01 (Marketplace Expansion & Native Integrations)

### Added
- Native connectors for Shopify, WooCommerce, Mailchimp, and HubSpot.
- CSV bulk upload and batch generation queue for catalogs up to 10,000 SKUs.
- Admin dashboard telemetry for active subscribers and campaign volume.

---

## [1.0.0] - 2026-07-01 (Initial General Availability)

### Added
- Core AI copywriting engine powered by Google Gemini.
- Multi-format generation: Product descriptions, ad copy, email sequences, and social media posts.
- Subscription billing integration with Stripe.
- REST API with API key authentication and rate limiting.
