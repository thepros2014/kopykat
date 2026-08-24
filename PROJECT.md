# KopyKat project guide

## Purpose

KopyKat is a Python/FastAPI application for AI-assisted e-commerce operations.
It combines authenticated content generation, catalog workflows, external
connectors, inventory reconciliation, review tooling, billing, and scheduled
marketing jobs.

This document describes the current repository shape. It is an engineering
reference, not a product roadmap, financial forecast, service-level agreement,
or statement that every external integration is production-certified.

## Current architecture

| Layer | Implementation | Notes |
| --- | --- | --- |
| HTTP/API | FastAPI and Uvicorn | Routes, validation, rate limits, middleware, health checks |
| Authentication | PyJWT, bcrypt, API-key hashes | JWT and kk_live_ API-key flows |
| Persistence | SQLAlchemy 2.0 | SQLite locally; managed PostgreSQL required in strict environments |
| AI adapters | OpenAI Responses API primary, Gemini fallback | Provider credentials and model availability are deployment concerns |
| Integrations | Marketplace adapters and OpenAPI connector runtime | Credentials are encrypted at rest; outbound URLs are validated |
| Background work | APScheduler | Runs in the web process with one worker by default |
| Browser clients | Static HTML/JavaScript and React/TypeScript | Both are maintained in the repository |
| Billing | Stripe checkout and webhooks | Requires configured price IDs and webhook signing secret |

## Source tree

```text
server/
  main.py                 FastAPI app, route registration, middleware, lifespan
  config.py               Environment-aware configuration
  auth.py                 Passwords, JWTs, API keys, Fernet encryption
  database.py             SQLAlchemy models and startup migrations
  models.py               Pydantic request and response models
  ai_engine.py            Listing optimization and copy generation
  gemini_client.py        Google Gen AI client adapter
  campaigns.py            Campaign and image-assisted generation
  connector_engine.py     SSRF-resistant HTTP and OpenAPI discovery
  connector_registry.py   Connector specification execution
  integrations.py         Marketplace and content-platform adapters
  inventory.py            Stock updates, reconciliation, and idempotency
  marketing.py            SEO, email drip, and opportunity scanning
  reviews_ugc.py          Review classification and post-purchase drafts
  pricing_monitor.py      Margin analysis and price recommendations
  billing.py              Stripe plans, checkout, and fulfillment
  scheduler.py            Scheduled maintenance and marketing jobs
  runtime.py              Validated container/process entry point

frontend/
  index.html, dashboard.html, admin.html, blog.html, post.html
  static/                 Shared browser assets

frontend/react-app/
  src/                    React and TypeScript application
  package.json             Frontend scripts and dependencies

tests/
  test_*.py                Unit, integration, security, adversarial, and UI checks
```

## Functional areas

### Content and campaigns

The API supports bounded copy generation through /api/generate, campaign
bundles through /api/campaign/generate, and image-assisted campaigns through
/api/campaign/generate-vision. The listing optimizer returns platform-shaped
drafts for Amazon, Shopify, Etsy, TikTok Shop, and eBay.

Generation endpoints reserve account credits before calling an AI provider.
Provider failures refund the reserved credits. The response reports the
remaining balance returned by the database.

### Connectors and catalog workflows

Users can save encrypted integration credentials, discover connector
specifications, test operations, import Shopify catalog data, and push
approved assets. Outbound HTTP includes URL validation, private-network
blocking, redirect controls, bounded responses, and DNS-rebinding defenses.

Provider support is not uniform. Some adapters are fully exercised by tests,
while others require provider-specific credentials and integration testing
before use.

### Inventory

Inventory records are scoped to the authenticated user. Stock events are
processed by SKU, recorded in the synchronization log, and can be reconciled
against a canonical quantity. Event identifiers are used for replay protection
when available.

### Growth and review tooling

The repository includes SEO article generation, sitemap and robots endpoints,
review sentiment classification, post-purchase draft sequences, price and
margin analysis, and a public-community opportunity scanner. Generated HTML
and user-visible content are sanitized or rendered through safe DOM APIs where
applicable.

Scheduled jobs require deliberate operational configuration. Email delivery,
AI calls, and public-community access should be tested with appropriate
accounts and rate limits before being enabled.

### Billing and entitlements

Stripe handles checkout and webhook fulfillment. Plans, generation packs, and
add-ons are defined in server/billing.py. Webhooks are signature-verified
and deduplicated by event ID. Billing routes return a configuration error when
required Stripe settings are absent; they do not silently simulate payment.

## Security model

- Strict staging and production startup rejects missing or weak secrets.
- Production and staging require an explicit PostgreSQL DATABASE_URL.
- JWT tokens include an authentication-version claim so password resets and
  revocation invalidate older tokens.
- API keys are returned once at creation and stored as hashes.
- Marketplace credentials and BYOK keys are encrypted with Fernet.
- Tenant-owned records are filtered by the authenticated user ID.
- Host, origin, proxy, request-size, and outbound-URL controls are bounded.
- Security headers, trusted-host checks, and production HSTS are configured by
  the FastAPI application in strict environments.

See SECURITY.md for reporting and deployment requirements.

## Development workflow

1. Copy .env.example to a local .env and use development-only values.
2. Run python -m server.runtime for the backend.
3. Run npm ci and npm run dev inside frontend/react-app when working on the
   React client.
4. Run python -m pytest -q before submitting a change.
5. Run the focused lint, dependency, security, and frontend checks described
   in TEST_READY.md.
6. Review git diff --check and confirm no secrets, database files, or local
   artifacts are staged.

## Operational boundaries

The codebase contains application-level controls, but a real deployment also
needs managed database backups, secret rotation, provider account controls,
logging and alerting, a restore drill, rate-limit capacity planning, and a
review of legal and platform terms for every connected service.

Do not infer customer or revenue status from the admin metrics endpoints.
Those values are calculated from the current database and are zero or empty
when the instance has no corresponding records.
