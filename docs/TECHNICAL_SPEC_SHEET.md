# KopyKat technical specification

Document status: repository reference
Application version: 2.0.0
Scope: current source tree, configuration, and tested application behavior

This document is intentionally evidence-based. It does not claim live
customers, revenue, valuation, throughput, uptime, regulatory compliance, or
provider certification. Those values require deployment-specific evidence.

## 1. System topology

```text
Browser clients and API consumers
              |
              v
FastAPI application
  authentication, validation, rate limits, request IDs,
  trusted hosts, CORS, security headers, health checks
              |
      +-------+--------+------------------+
      |                |                  |
      v                v                  v
Domain services   SQLAlchemy         APScheduler
AI, campaigns,    models and         maintenance and
connectors,       transactions       marketing jobs
inventory,
billing, growth
      |                |
      v                v
External providers  SQLite locally
AI, Stripe,         PostgreSQL in
marketplaces,      staging/production
email, monitoring
```

The process entry point starts one Uvicorn worker by default. This is
intentional because the in-process scheduler must not be duplicated
accidentally. Horizontal scaling requires multiple service instances with
coordinated job ownership or a separate worker service.

## 2. Application components

| Component | Responsibility |
| --- | --- |
| FastAPI gateway | Route registration, dependency injection, validation, rate limits, health |
| Authentication | Password hashing, JWT sessions, API-key hashes, token revocation |
| Credential vault | Fernet encryption for marketplace credentials and BYOK keys |
| AI layer | Provider adapters, bounded prompts, structured output and fallbacks |
| Campaign service | Text and image-assisted campaign asset assembly |
| Connector runtime | OpenAPI discovery, connector execution, outbound network controls |
| Inventory service | SKU quantities, event replay protection, fanout, reconciliation |
| Growth service | SEO articles, sitemap, review analysis, drip drafts, opportunity scanning |
| Billing service | Stripe checkout, signed webhooks, plans, packs, and entitlements |
| Browser clients | Static HTML/JavaScript client and React/TypeScript client |

## 3. HTTP and API surface

### Public and system routes

- `/` and `/dashboard` serve the static browser experience.
- `/health` reports process health.
- `/ready` reports application readiness.
- `/robots.txt` and `/sitemap.xml` expose public indexing metadata.
- `/api/plans` exposes the configured plan and generation-pack catalog.
- `/api/docs` and `/api/openapi.json` are disabled in strict environments
  unless explicitly enabled.

### Authenticated route groups

- `/auth/*`: registration, login, email verification, password reset, and
  current-user information.
- `/api/keys`: create, list, and revoke API keys.
- `/api/generate`: bounded single-copy generation.
- `/api/campaign/*`: campaign generation, image-assisted generation, and
  controlled push jobs.
- `/api/connector/*` and `/api/integrations`: connector discovery, credentials,
  status, testing, and legacy integration storage.
- `/api/catalog/*`: CSV parsing and Shopify import.
- `/api/inventory/*`: inventory records, webhooks, reconciliation, and logs.
- `/api/reviews/*`: post-purchase drafts and customer review analysis.
- `/api/pricing/*`: price and margin records.
- `/api/brand-persona` and `/api/optimizer/marketplace-listing`: optional
  brand-voice and listing-optimization workflows.
- `/billing/*`: Stripe checkout, webhook intake, and subscription status.
- `/api/seo/*`, `/api/drip/*`, and `/api/leads`: growth-engine analytics.

Bearer JWTs are used for browser sessions. API keys can be supplied as bearer
credentials for programmatic access where the route permits them. Route-level
dependencies determine which credential types are accepted.

## 4. Persistence model

The primary SQLAlchemy entities are:

| Entity | Purpose |
| --- | --- |
| User | Account, plan, generation balances, and encrypted BYOK metadata |
| APIKey | Hashed programmatic credential and usage counters |
| Subscription | Stripe subscription state and billing period |
| RevenueRecord | Persisted successful payment records |
| StripeEvent | Webhook event idempotency ledger |
| UsageRecord | Request and generation accounting |
| UserIntegration | Encrypted external-platform credentials |
| Connector | Discovered connector metadata and operations |
| Campaign and PushJob | Generated assets and asynchronous push work |
| InventoryItem and InventorySyncLog | SKU state and stock audit trail |
| CustomerReview and DripLog | Review analysis and delivery idempotency |
| PriceMarginItem | Unit-economics calculations and recommendations |
| BlogPost and OpportunityLog | SEO content and public-opportunity drafts |
| BrandPersona and UserEntitlement | User voice configuration and add-on access |

Production and staging require an explicitly configured managed PostgreSQL
database. SQLite is supported for local development and tests only.

## 5. Security controls

- Strict environments reject placeholder or weak JWT, admin, and encryption
  secrets during startup.
- Password inputs are bounded for the bcrypt backend.
- JWTs carry an authentication-version claim; reset and revocation operations
  invalidate older versions.
- API keys are shown only at creation and persisted as hashes.
- Integration and BYOK secrets are encrypted before database persistence.
- Tenant-owned queries include the authenticated user identifier.
- Request bodies, image uploads, CSV inputs, connector responses, and generated
  content have explicit limits.
- Trusted-host, CORS, proxy, request-ID, and security-header middleware are
  applied centrally.
- Outbound requests reject unsafe schemes and private or metadata networks,
  disable implicit proxy environment use, block redirects where appropriate,
  and bound response reads.
- Generated HTML is sanitized before persistence or output.

See SECURITY.md for the reporting process and deployment security baseline.

## 6. Quota and billing behavior

Generation reservations consume monthly credits before purchased credits. A
failed upstream generation restores the exact reservation. Stripe events are
signature-verified and deduplicated by event ID before fulfillment.

The plan registry is the source of truth for application-side prices,
entitlements, and generation limits. Checkout still requires matching Stripe
price IDs and a configured signing secret. Unconfigured billing returns a
service-configuration error instead of pretending that payment succeeded.

## 7. Scheduled jobs

The scheduler uses UTC and is created during application startup:

| Job | Schedule |
| --- | --- |
| API counter reset | Daily at 00:00 |
| Subscription health | Daily at 02:00 |
| Usage cleanup | Sunday at 03:00 |
| Revenue report | Daily at 08:00 |
| Email drip | Daily at 10:00 |
| Opportunity scout | Every four hours at minute 15 |
| SEO generation | Monday, Wednesday, and Friday at 14:00 |

Jobs depend on database access and, depending on the job, AI, email, or public
provider access. They should be observed and tested in the deployment where
they are enabled.

## 8. Dependency and runtime baseline

The pinned runtime baseline is defined by requirements.txt:

- Python 3.11 or newer
- FastAPI, Uvicorn, Pydantic, SQLAlchemy, and psycopg2-binary
- PyJWT, bcrypt, cryptography, and python-multipart
- HTTPX, SlowAPI, Bleach, and python-dotenv
- Google Gen AI and OpenAI SDKs
- Stripe, APScheduler, Sentry SDK, and supporting utilities

The React client uses React 18, TypeScript, Vite, Lucide React, and the
checked-in npm lockfile.

## 9. Deployment prerequisites

Before production use, provide:

1. Managed PostgreSQL with backups, monitoring, and a restore drill.
2. Secret-manager values for all strict configuration settings.
3. HTTPS termination, exact host/origin allowlists, and trusted proxy values.
4. Stripe test-mode validation followed by signed production webhooks.
5. Provider-specific integration tests using non-production merchant accounts.
6. Log redaction, alerting, support ownership, and rollback procedures.
7. A decision about scheduler ownership before adding web workers.

No target SLA or performance benchmark is specified in this document. Establish
those from measured workload tests in the actual deployment environment.
