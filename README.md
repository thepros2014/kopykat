# KopyKat — Autonomous E-Commerce Operating System

[![Build Status](https://img.shields.io/github/actions/workflow/status/thepros2014/kopykat/ci.yml?branch=main&label=Build&style=flat-square)](https://github.com/thepros2014/kopykat/actions)
[![Test Suite](https://img.shields.io/badge/Tests-62%20Passing-brightgreen?style=flat-square)](https://github.com/thepros2014/kopykat)
[![Python Version](https://img.shields.io/badge/Python-3.11-blue?style=flat-square&logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![Stripe](https://img.shields.io/badge/Stripe-Billing%20Live-635BFF?style=flat-square&logo=stripe)](https://stripe.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Zero Emojis](https://img.shields.io/badge/Policy-Zero%20Emojis-black?style=flat-square)](tests/test_no_emojis.py)


KopyKat is a multi-channel e-commerce automation and marketing engine. It synchronizes catalogs across Shopify, Amazon, eBay, Walmart, and Temu, mines competitor 1-star reviews to generate high-converting counter-copy, balances cross-platform stock levels in real time to prevent overselling, and automates SEO blogs, email drips, and lead discovery.

---

## Architecture Overview

### 1. Component Diagram

```mermaid
graph TD
    User([Merchant / Dashboard]) -->|HTTPS / JWT| API[FastAPI Gateway]
    StoreHooks([Shopify / Marketplaces]) -->|Webhooks / Orders| API
    
    subgraph Core Backend
        API --> Auth[Auth & API Key Engine]
        API --> Billing[Stripe Billing & BYOK Engine]
        API --> Catalog[Catalog Importer & Semantic CSV]
        API --> Inventory[Cross-Platform Stock Balancer]
        API --> AI[AI Copy & Vision Engine]
        API --> Reviews[Competitor Miner & UGC Hub]
        API --> PriceMon[Price & Margin Monitor]
        API --> Connectors[Universal OpenAPI Connectors]
    end

    subgraph Autonomous Background Workers
        Cron[APScheduler Daemon]
        Cron -->|3x / Week| SEO[SEO Blog Engine]
        Cron -->|Daily| Drip[Email Conversion Bot]
        Cron -->|Every 4 Hours| Scout[Social Opportunity Scout]
    end

    subgraph Storage Layer
        DB[(PostgreSQL / SQLite Database)]
        Vault[Fernet Encrypted Key Store]
    end

    subgraph External Platforms
        Shopify[Shopify Admin API]
        Amazon[Amazon SP-API]
        Ebay[eBay Inventory API]
        Walmart[Walmart Marketplace]
        Gemini[Google Gemini Vision / Text AI]
        OpenAI[OpenAI BYOK Cluster]
        Stripe[Stripe API & Webhooks]
    end

    Auth --> DB
    Auth --> Vault
    Billing --> DB
    Billing --> Stripe
    Catalog --> DB
    Catalog --> Shopify
    Inventory --> DB
    Inventory --> Shopify
    Inventory --> Amazon
    Inventory --> Ebay
    Inventory --> Walmart
    AI --> Gemini
    AI --> OpenAI
    Reviews --> DB
    PriceMon --> DB
    Connectors --> Vault
```

---

### 2. Data Flow Diagram

```mermaid
sequenceDiagram
    autonumber
    actor Merchant as Store Merchant
    participant Web as Web Dashboard
    participant API as FastAPI Server
    participant Inv as Inventory Balancer
    participant AI as AI Engine
    participant Ext as Connected Marketplaces (eBay, Amazon, Walmart)

    %% Flow 1: 1-Click Catalog Import & Syndication
    Merchant->>Web: 1-Click Import Catalog from Shopify
    Web->>API: POST /api/catalog/import-shopify
    API->>Shopify: GET /admin/api/2024-01/products.json
    Shopify-->>API: Raw Product Data & Media
    API-->>Web: Normalized Product Catalog Items
    
    Merchant->>Web: Select Products & Click "Syndicate"
    Web->>API: POST /api/campaign/generate (Batch)
    API->>AI: Generate Descriptions, SEO Blog, Drips
    AI-->>API: Enriched Multi-Platform Assets
    API->>Ext: Fanout Deployments in Parallel
    Ext-->>API: HTTP 200 Deployment Acknowledged
    API-->>Web: Syndication Complete

    %% Flow 2: Real-time Order & Inventory Balancing
    Shopify->>API: POST /api/inventory/webhook/shopify (Order Created: -1 Unit)
    API->>Inv: sync_inventory_across_platforms(sku, delta=-1)
    Inv->>Inv: Atomically decrement total_stock in DB
    Inv->>Ext: Fanout Stock Update to eBay, Amazon, Walmart (Skip Shopify)
    Ext-->>Inv: Stock Adjusted
    Inv-->>API: Sync Log Committed
```

---

### 3. Background Cron Job Schedules

```mermaid
gantt
    title Autonomous Background Worker Schedules
    dateFormat X
    axisFormat %H:%M

    section SEO Blog Bot
    Draft & Publish Store Article (Mon/Wed/Fri 09:00 UTC) :active, seo1, 0, 10
    
    section Conversion Drip Bot
    Process Day 1, 3, 7 User Nurture Sequences (Daily 10:00 UTC) :drip1, 10, 20

    section Social Opportunity Scout
    Scan Reddit & Social Discussions (Every 4 Hours) :scout1, 0, 5
    Scan Reddit & Social Discussions :scout2, 240, 245
    Scan Reddit & Social Discussions :scout3, 480, 485
    Scan Reddit & Social Discussions :scout4, 720, 725
```

---

## Module Map & Capabilities

| Module | Core Responsibility | Key Endpoints | Supported Channels |
|---|---|---|---|
| **Module 1: Competitor Review Miner** | Ingests 1-star competitor reviews to generate counter-copy, comparison tables, and ad angles. | `POST /api/competitor/mine-reviews` | Universal Copy |
| **Module 2: Inventory Balancer** | Real-time stock synchronization across platforms on order events to prevent overselling. | `POST /api/inventory/webhook/{platform}`, `GET /api/inventory` | Shopify, Amazon, eBay, Walmart, Temu |
| **Module 3: Review & UGC Drip Hub** | Generates 3-step post-purchase review sequences and classifies sentiment of customer feedback. | `POST /api/reviews/drip-templates`, `POST /api/reviews/submit` | Email / Storefront Webhooks |
| **Module 4: Price & Margin Monitor** | Unit economics engine tracking COGS, profit per unit, margin health, and competitor price shifts. | `POST /api/pricing/item`, `GET /api/pricing/items` | Catalog SKUs |
| **Module 5: Shopify Direct Import** | 1-click direct catalog fetch via Shopify Admin API without manual CSV exports. | `POST /api/catalog/import-shopify` | Shopify Admin REST |
| **BYOK Enterprise AI Infrastructure** | Megastore tier support for custom private OpenAI and Google Gemini API keys. | `POST /api/user/custom-ai-key` | OpenAI, Gemini |

---

## Pricing Tiers

- **Test Drive ($0 / mo):** 5 monthly campaigns, 1 connected platform of choice, core engine preview.
- **Boutique Store ($179.49 / mo):** 150 monthly campaigns, 2 connectors of choice, 1 automation feature (CSV or Auto-Sync), Review Miner.
- **Standard Store ($379.49 / mo):** 1,000 monthly campaigns, 10 connectors of choice, 2 automations (CSV + Vision AI), Universal Connectors.
- **Megastore Infrastructure ($9,639.63 / mo):** 2,500 monthly campaigns (using platform cloud) or **UNLIMITED** campaigns via Bring-Your-Own-Key (BYOK), all connectors and automations included, dedicated high-throughput cluster.

---

## Tech Stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.0, Uvicorn, SlowAPI, Bleach, Pydantic V2
- **Database:** PostgreSQL / SQLite with Fernet credential encryption
- **AI Infrastructure:** Google Gemini (`gemini-flash-latest`), OpenAI GPT-4o
- **Billing:** Stripe Subscriptions, One-Time Packs, and Webhooks
- **Frontend:** Vanilla HTML5, CSS3, ES6 JavaScript (Zero dependencies, XSS-safe DOM)
- **CI / CD:** GitHub Actions (Pytest, Black, Flake8, Bandit)

---

## Documentation Links

- [API Authentication](docs/api/auth.md)
- [API Billing & BYOK](docs/api/billing.md)
- [API Content & Campaign Generation](docs/api/generation.md)
- [API Inventory Balancer](docs/api/inventory.md)
- [Technical Spec Sheet](docs/SPEC_SHEET.md)
- [Operator Tutorial](docs/TUTORIAL.md)
