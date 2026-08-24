# KopyKat system specification

## Scope and status

KopyKat is an AI-assisted e-commerce operations service. This sheet is a
compact reference to the current repository. It is not a claim of live
customer adoption, revenue, uptime, capacity, or provider certification.

## Runtime

| Area | Current implementation |
| --- | --- |
| Backend | Python 3.11+, FastAPI, Uvicorn, Pydantic, SQLAlchemy |
| Database | SQLite for local development/tests; managed PostgreSQL for strict environments |
| AI providers | OpenAI Responses API adapter and Google Gen AI adapter |
| Web clients | Static HTML/JavaScript and React/TypeScript with Vite |
| Payments | Stripe Checkout and signed webhook processing |
| Background work | APScheduler in the single default web process |
| Security | JWT/API keys, bcrypt, Fernet, tenant scoping, request and network limits |

## Functional modules

### Content generation

- Single-copy generation through /api/generate.
- Campaign bundles through /api/campaign/generate.
- Image-assisted generation through /api/campaign/generate-vision.
- Platform-shaped listing drafts through /api/optimizer/marketplace-listing.
- Optional provider selection through AI_PROVIDER, OPENAI_API_KEY, and
  GEMINI_API_KEY.

### Commerce operations

- CSV parsing and Shopify catalog import.
- Saved integrations with encrypted credentials.
- Connector discovery and bounded connector execution.
- SKU inventory records, authenticated events, fanout, reconciliation, and
  audit logs.
- Price, cost, competitor-price, margin, and recommendation records.

### Growth operations

- Sanitized SEO articles and dynamic sitemap/robots routes.
- Review sentiment analysis and draft responses.
- Post-purchase message templates.
- Scheduled opportunity scanning that records drafts for human review.
- OpenAI or Gemini can generate internal drafts when configured.

The service does not autonomously publish commercial outreach to social
networks. External posting requires an approved integration, platform
permission, and human review.

## Data and security invariants

- User-owned records are filtered by authenticated user ID.
- JWT versions are invalidated after password resets or revocation events.
- API keys are displayed once and stored as hashes.
- Marketplace and AI credentials are encrypted before persistence.
- Generation credits are reserved before provider work and refunded after
  provider failure.
- Stripe and inventory event IDs are deduplicated.
- Outbound URLs are validated against unsafe schemes and private networks.
- Redirects, request bodies, image uploads, CSV inputs, and responses are
  bounded.
- Generated HTML is sanitized and browser output uses safe rendering paths.

## Required production configuration

Set ENVIRONMENT to staging or production and provide:

- DATABASE_URL using managed PostgreSQL.
- JWT_SECRET_KEY with at least 32 random characters.
- A valid INTEGRATION_ENCRYPTION_KEY Fernet key.
- ADMIN_SECRET with at least 24 random characters.
- An HTTPS APP_BASE_URL.
- Narrow ALLOWED_HOSTS, ALLOWED_ORIGINS, and TRUSTED_PROXIES values.
- Provider, payment, email, and monitoring settings for enabled features.

## Verification

Use TEST_READY.md for the full procedure. The minimum backend checks are:

```powershell
python -m pytest -q
python -m compileall -q server tests
python -m flake8 server tests --select=E9,F63,F7,F82 --count --statistics
python -m bandit -r server -ll -ii -x server/tests,tests
python -m pip_audit -r requirements.txt
```

Build the React client and audit its lockfile before deployment:

```powershell
Set-Location frontend/react-app
npm ci
npm run build
npm audit --audit-level=high
```

## Operational limitations

Passing repository tests does not replace provider integration tests, database
restore testing, backup validation, incident response, or a review of the
terms governing each external service.
