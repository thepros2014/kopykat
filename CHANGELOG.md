# KopyKat changelog

This file records notable repository changes using the general structure of
Semantic Versioning. A changelog entry describes source changes; it does not
certify a deployment, imply customer adoption, or replace release notes and
operational approval.

## [Unreleased] - 2026-08-23

### Security and reliability

- Added environment-aware startup validation that fails closed for missing
  production and staging secrets or a non-PostgreSQL database.
- Hardened authentication with bounded credentials, token-version revocation,
  inactive-user checks, normalized emails, and API-key hygiene.
- Added request IDs, security headers, trusted-host handling, bounded request
  bodies, and stricter CORS and proxy configuration.
- Hardened outbound connector and Shopify-import requests against SSRF,
  private-network access, redirects, DNS rebinding, unbounded responses, and
  proxy environment leakage.
- Kept credential and BYOK storage encrypted and removed source-controlled
  fallback secrets.

### Platform and maintenance

- Migrated Google AI calls to the current repository adapter in
  server/gemini_client.py and the google-genai dependency.
- Added a production-hardening test module and expanded checks around
  truthful metrics, configuration, HTTP boundaries, and generated content.
- Updated the React/Vite toolchain and checked the generated npm lockfile.
- Added frontend dependency auditing to CI and documented backend dependency,
  lint, security, and build verification.
- Reworked the public documentation to remove unsupported customer, revenue,
  benchmark, and valuation claims.

## [2.0.0] - 2026-08-23

### Added

- FastAPI routes for authenticated copy generation, campaign generation,
  marketplace listing optimization, inventory, reviews, pricing, connectors,
  billing, and administrative telemetry.
- Static and React browser clients.
- Stripe subscriptions, generation packs, add-ons, and encrypted BYOK
  configuration.
- Scheduled SEO, email, opportunity-scanning, maintenance, and reporting jobs.
- Test coverage for authentication, billing, campaigns, connectors, inventory,
  security boundaries, frontend behavior, and adversarial cases.

### Changed

- Consolidated platform and request validation in Pydantic models.
- Added tenant-scoped persistence queries and idempotent webhook handling.
- Added safe HTML handling for generated content and safe DOM rendering in the
  browser clients.

## [1.3.0] - 2026-08-20

### Added

- OpenAPI-based connector discovery.
- Inventory reconciliation and multi-channel synchronization primitives.
- Price and margin analysis for catalog items.

### Fixed

- Corrected concurrent webhook processing and API-key handling.

## [1.2.0] - 2026-08-15

### Added

- Review and user-generated-content workflows.
- Competitor review analysis and brand-persona configuration.
- Scheduled post-purchase draft sequences.

## [1.1.0] - 2026-08-01

### Added

- Native marketplace and content-platform integration adapters.
- CSV catalog parsing and batch campaign workflows.
- Administrative usage and billing views.

## [1.0.0] - 2026-07-01

### Added

- Initial FastAPI service and browser dashboard.
- Core AI copy-generation workflows.
- Stripe billing integration.
- Bearer-token and API-key authentication.
