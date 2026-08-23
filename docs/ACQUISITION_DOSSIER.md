# KopyKat — Technical Asset & Software Acquisition Dossier

---

## Executive Overview

KopyKat is an autonomous, multi-channel e-commerce operating system and copywriting SaaS designed for hands-off scalability. The platform automates catalog ingestion, multi-marketplace syndication (Shopify, Amazon, eBay, Walmart, Temu), real-time loop-free inventory balancing, customer review sentiment mining, competitor counter-copy generation, and background marketing (SEO blog generation, conversion email drips, and Reddit lead discovery).

---

## 1. Core Proprietary IP & Architecture Assets

### Autonomous Growth & Marketing Workers
1. **SEO Blog Engine (`APScheduler`):** Autonomously researches high-intent buyer keywords, drafts 800-word structured HTML articles, sanitizes markup, publishes to the database, generates dynamic XML sitemaps, and pings search crawlers (Google & Bing).
2. **Email Conversion Drip Bot:** Evaluates user lifecycle milestones (Days 2, 4, 7) and executes automated value-first onboarding and upgrade drips with strict idempotency tracking.
3. **Social Opportunity Scout:** Ingests public Reddit discussions across entrepreneurship and e-commerce subreddits every 4 hours, analyzes buyer intent (1-100 scoring algorithm), drafts tailored contextual replies, and streams leads directly to the dashboard.

### Flagship E-Commerce Modules
1. **Competitor 1-Star Review Miner:** Ingests negative competitor customer reviews, extracts root flaws, and crafts counter-positioned listing copy and direct-response ad angles.
2. **Cross-Platform Inventory Balancer:** Intercepts purchase webhooks (`orders/create`), atomically decrements total database quantities, and fans out updates across connected storefronts with loop-prevention heuristics.
3. **Post-Purchase Review & UGC Drip Hub:** Generates 3-step post-delivery customer nurture emails with coupon incentives and automatically classifies customer sentiment with draft resolution replies.
4. **Automated Price & Margin Monitor:** Real-time unit economics engine tracking Cost of Goods Sold (COGS), profit per unit, margin health (< 15% alert), and competitor price benchmarking.
5. **Direct 1-Click Shopify Catalog Importer:** Zero-CSV direct product catalog sync via Shopify Admin API with HTML description normalization.

### Enterprise Bring-Your-Own-Key (BYOK) Cluster
- High-tier Megastore accounts ($9,639.63/mo) can connect private OpenAI and Google Gemini API keys.
- All credentials are encrypted at rest using Fernet symmetric encryption (`cryptography.fernet`).
- Bypasses cloud quota limits to execute unlimited multi-channel campaigns on KopyKat infrastructure.

---

## 2. Infrastructure & Code Quality Standards

- **Backend Runtime:** Python 3.11, FastAPI, SQLAlchemy 2.0 ORM, SlowAPI rate limiting, Bleach HTML sanitization, Pydantic V2 validation.
- **Database Support:** PostgreSQL (Neon.tech / AWS RDS / Supabase) and SQLite with automatic schema migrations.
- **CI/CD Pipeline:** 5-stage GitHub Actions workflow encompassing Black formatting, Flake8 linting, Mypy type validation, Bandit security scanning, Safety dependency audits, and automated Pytest execution with Codecov reporting.
- **Test Suite Coverage:** 44+ automated integration and unit tests passing with 100% green status.
- **Release Versioning:** Semantic release tags (`v0.1.0` through `v1.0.0`) tagged and pushed on Git.
- **Codebase Policy:** Strict Zero-Emoji standard enforced across all backend code, frontend assets, tests, and documentation.

---

## 3. Financial Model & Monetization Capabilities

### Monthly Subscription Tiers
- **Test Drive:** $0.00 / mo (5 campaigns, 1 connector).
- **Boutique Store:** $179.49 / mo (150 campaigns, 2 connectors, 1 automation).
- **Standard Store:** $379.49 / mo (1,000 campaigns, 10 connectors, 2 automations).
- **Megastore Infrastructure:** $9,639.63 / mo (2,500 cloud campaigns or UNLIMITED with BYOK API key).

### High-Margin À-La-Carte Add-Ons
- **Brand Voice Training (Custom AI Persona):** $49.00 one-time / $19.00/mo.
- **Marketplace Listing Optimizer Pack (50 Listings):** $29.00 one-time.
- **Done-For-You Monthly Marketing Pack:** $149.00 / mo.
- **Unlimited Bulk Catalog Import Pass:** $19.00 one-time.
- **One-Time Generation Packs:** $5 (Starter), $15 (Growth), $40 (Scale).

---

## 4. Deployment & Handover Readiness

- **Hosting Platform:** Render.com (Web Service + PostgreSQL)
- **Containerization:** Production-ready `Dockerfile` with multi-stage dependency caching
- **Environment Configuration:** Comprehensive `.env.example` with required, optional, and security directives
- **Documentation Suite:** Complete `/docs` catalog covering API authentication, billing, AI generation, inventory balancing, SEO engines, drip bots, Reddit scouts, and technical specifications
