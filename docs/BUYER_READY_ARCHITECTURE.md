# KopyKat technical architecture and readiness dossier

Document status: engineering reference
Application version: 2.0.0

This dossier is suitable for technical review of the repository. It is not a
financial forecast, valuation, customer reference, security certification, or
claim that the application is ready for an unreviewed production launch. The
repository currently makes no live customer or revenue claim.

## 1. Product scope

KopyKat combines:

- AI-assisted copy and image-to-campaign generation.
- Marketplace listing drafts and catalog workflows.
- Encrypted integrations and connector discovery.
- SKU inventory tracking, event processing, fanout, and reconciliation.
- Review analysis, post-purchase drafts, SEO content, and margin analysis.
- Stripe billing, generation packs, add-ons, and optional BYOK.
- Scheduled internal jobs that produce drafts and operational records.

The system is designed for reviewable automation. It does not silently publish
generated marketing content to third-party communities.

## 2. Architecture

```text
              Browser clients and API consumers
                              |
                              v
                      FastAPI application
     auth | validation | rate limits | security headers | health
                              |
       +----------------------+----------------------+
       |                      |                      |
       v                      v                      v
   AI and campaign       Connector and          Billing and
   generation            catalog services       growth services
       |                      |                      |
       +----------------------+----------------------+
                              |
                              v
                 SQLAlchemy transaction boundary
                              |
              +---------------+----------------+
              |                                |
              v                                v
        PostgreSQL in                    SQLite for
        strict environments              local/test use
```

The default runtime starts one web worker because APScheduler belongs to the
application process. A scaled deployment must define job ownership before
adding workers or instances.

## 3. Security and isolation

The current application includes:

- Fail-closed production and staging checks for secrets, database type, and
  HTTPS base URL.
- JWT authentication with authentication-version invalidation.
- Bcrypt password hashing with bounded password inputs.
- One-time API-key display and SHA-256 key storage.
- Fernet encryption for marketplace credentials and BYOK keys.
- User-scoped database queries for tenant-owned records.
- Trusted-host, CORS, proxy, request-size, request-ID, and security-header
  controls.
- SSRF protections for connector discovery and outbound provider requests.
- Bounded response reads and redirect controls.
- Sanitization of generated HTML and safe frontend rendering.
- Idempotency ledgers for Stripe and inventory events.

These controls are application-level defenses. A production review must also
cover the host, database, secret manager, network, identity provider, logs,
backups, and provider accounts.

## 4. Provider and integration boundaries

The code contains adapters for Amazon, Shopify, Etsy, TikTok Shop, eBay,
Walmart, Temu, WooCommerce, WordPress, Mailchimp, HubSpot, and Webflow. The
available operations and test depth vary by adapter. Each enabled provider
requires a non-production integration test using scoped credentials.

The AI layer supports OpenAI and Google Gen AI. OpenAI is configured with
OPENAI_API_KEY, OPENAI_MODEL, and AI_PROVIDER. Gemini uses GEMINI_API_KEY and
GEMINI_MODEL. Provider calls are not made during the repository test
environment.

## 5. Billing and data ownership

The plan registry in server/billing.py defines application-side plans,
generation limits, packs, add-ons, and entitlements. Stripe remains the
payment-system source of truth and must be configured with matching price IDs
and webhook signing secrets.

The repository does not assert current MRR, ARR, customers, margins,
valuation, or conversion rates. Administrative metrics are calculated from
records present in the running database.

## 6. Readiness checklist

| Control | Repository evidence | Deployment evidence still required |
| --- | --- | --- |
| Authentication and tenant scoping | Tests and route dependencies | Penetration test and identity policy |
| Secret handling | Strict config and encrypted credentials | Secret manager, rotation, access review |
| Database | SQLAlchemy models and startup checks | Managed service, backups, restore drill |
| Outbound network safety | URL validation and bounded clients | Egress policy and provider allowlist |
| Billing | Signed and deduplicated webhooks | Stripe test/live verification |
| AI providers | Shared adapters and fallback paths | Account limits, model approval, cost controls |
| Scheduled jobs | UTC schedules and single-worker default | Job ownership, alerting, retry policy |
| Frontend | Safe rendering tests and production build | Browser, accessibility, and device review |
| Monitoring | Optional Sentry and structured logs | Alert routing and incident ownership |

## 7. Recommended diligence package

For a release or transaction review, collect:

1. The commit identifier and dependency lockfiles.
2. Current test, build, and dependency-audit output.
3. A data-flow map showing secrets, customer content, and provider payloads.
4. Database schema, migration, backup, and restore evidence.
5. Provider contracts, account scopes, and integration-test records.
6. Incident, support, data deletion, and key-rotation procedures.
7. Measured workload results from the target hosting environment.

No performance or service-level target is implied until those measurements and
operational controls are documented.
