# KopyKat

KopyKat is an AI-assisted e-commerce operations platform for generating
marketing content, organizing catalog workflows, connecting external
platforms, and monitoring inventory and unit economics from one API and
dashboard.

> Repository status: active engineering project. This repository does not
> make live customer, revenue, valuation, service-level, or throughput claims.
> A passing test suite is evidence of tested behavior, not a production
> certification.

[![Build](https://img.shields.io/github/actions/workflow/status/thepros2014/kopykat/ci.yml?branch=main&label=build)](https://github.com/thepros2014/kopykat/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-ASGI-009688)](https://fastapi.tiangolo.com/)

## Capabilities

- Generate product descriptions, ads, email content, social posts, and other
  bounded copy through authenticated API endpoints.
- Produce channel-specific listing drafts for Amazon, Shopify, Etsy, TikTok
  Shop, and eBay.
- Build campaign bundles containing blog, email, and social assets, including
  image-assisted generation when an AI provider is configured.
- Import catalog data from CSV or Shopify and push approved content through
  configured integrations.
- Track inventory by SKU, process authenticated inventory events, reconcile a
  canonical quantity, and record synchronization results.
- Classify customer reviews, draft responses, create post-purchase sequences,
  and calculate price and margin recommendations.
- Run scheduled SEO, email, and opportunity-scanning jobs when the required
  provider and delivery configuration is present.
- Use Stripe subscriptions, one-time generation packs, add-ons, and encrypted
  BYOK configuration where enabled for the account.

External platform actions are credential-dependent. A connector being present
in the registry does not mean that a production account has been connected or
that a provider operation has been verified for a specific merchant.

## Architecture

```text
Browser or API client
        |
        v
FastAPI application (auth, rate limits, validation, security headers)
        |
        +--> Domain services: AI, campaigns, connectors, inventory, billing
        |
        +--> SQLAlchemy persistence
        |        |
        |        +--> PostgreSQL in staging/production
        |        +--> SQLite for local development and tests
        |
        +--> External providers: AI, Stripe, marketplaces, email, Sentry
        |
        +--> APScheduler jobs owned by the single application process
```

The repository contains two browser clients:

- `frontend/` contains the lightweight HTML dashboard and public pages.
- `frontend/react-app/` contains the React and TypeScript application.

Production runs with one application worker by default because the scheduler
is owned by the web process. Scale with multiple service instances or move
scheduled work to a dedicated worker after designing job coordination.

## Repository layout

| Path | Purpose |
| --- | --- |
| `server/main.py` | FastAPI application, routes, middleware, and lifespan |
| `server/auth.py` | Password hashing, JWT/API-key authentication, and credential encryption |
| `server/config.py` | Environment-aware configuration and fail-closed production checks |
| `server/database.py` | SQLAlchemy models, engine setup, and lightweight migrations |
| `server/ai_engine.py` | Listing optimization and copy generation |
| `server/campaigns.py` | Text and image-assisted campaign assembly |
| `server/integrations.py` | Marketplace and legacy integration adapters |
| `server/connector_engine.py` | OpenAPI discovery and SSRF-resistant outbound HTTP |
| `server/inventory.py` | Inventory updates, fanout, reconciliation, and idempotency |
| `server/marketing.py` | SEO, email drip, and opportunity-scanning jobs |
| `server/billing.py` | Stripe checkout, webhook fulfillment, plans, and add-ons |
| `frontend/` | Static browser client |
| `frontend/react-app/` | React/Vite client |
| `tests/` | Unit, integration, adversarial, security, and frontend checks |
| `docs/` | API references, operations notes, and technical documentation |

## Requirements

- Python 3.11 or newer.
- A recent Node.js LTS release for the React application.
- SQLite for local development, or PostgreSQL for staging and production.
- Provider credentials only for the features being exercised.

## Local setup

Create a virtual environment and install the backend dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Review `.env` before starting the server. Local development can use the
SQLite default, but the generated secrets are process-local and must not be
used for persistent or shared environments.

Start the API and static client:

```powershell
python -m server.runtime
```

The default local address is `http://127.0.0.1:10000`. The health endpoints
are `/health` and `/ready`.

Build the React client:

```powershell
Set-Location frontend/react-app
npm ci
npm run build
```

Use `npm run dev` for an interactive frontend development server. Configure
its API base URL according to the local development setup before relying on
it for browser testing.

## Configuration

The complete configuration template is [.env.example](.env.example). The
following settings are required for a strict staging or production startup:

| Setting | Requirement |
| --- | --- |
| `ENVIRONMENT` | `staging` or `production` |
| `DATABASE_URL` | Explicit managed PostgreSQL URL |
| `JWT_SECRET_KEY` | Random value of at least 32 characters |
| `INTEGRATION_ENCRYPTION_KEY` | Valid Fernet key |
| `ADMIN_SECRET` | Secret of at least 24 characters |
| `APP_BASE_URL` | HTTPS public URL |
| `ALLOWED_HOSTS` | Exact hostnames accepted by the service |
| `ALLOWED_ORIGINS` | Exact browser origins required by the deployment |
| `TRUSTED_PROXIES` | Only proxy addresses that are actually trusted |

### AI provider configuration

OpenAI is the primary backend provider for copy generation, campaign vision,
and scheduled marketing drafts. Configure it in the local `.env` file or in
the deployment secret manager:

~~~dotenv
AI_PROVIDER=openai
OPENAI_API_KEY=your_server_side_key
OPENAI_MODEL=gpt-4o-mini
~~~

The key must remain server-side and must never be committed or placed in
browser code. Gemini is retained as an optional fallback for supported
workflows when `GEMINI_API_KEY` is also configured. The complete, non-secret
template is [.env.example](.env.example). Render receives `AI_PROVIDER` and
`OPENAI_MODEL` from `render.yaml`; add the real `OPENAI_API_KEY` in the
service's secret environment settings and redeploy.

Keep API documentation disabled in production unless an operator explicitly
needs it. Configure AI, Stripe, email, and marketplace credentials through a
secret manager rather than source control.

## API surface

The principal route groups are:

- `/auth/*` for registration, login, verification, password reset, and the
  current user.
- `/api/generate` and `/api/campaign/*` for copy and campaign generation.
- `/api/connector/*`, `/api/integrations`, and `/api/catalog/*` for external
  platform workflows.
- `/api/inventory/*`, `/api/reviews/*`, and `/api/pricing/*` for merchant
  operations.
- `/billing/*` and `/api/plans` for billing.
- `/health` and `/ready` for service checks.

Interactive OpenAPI documentation is available at `/api/docs` only when
`ENABLE_API_DOCS=true`. See the [API documentation](docs/api/auth.md) and the
[documentation index](docs/TUTORIAL.md) for examples.

## Verification

Run the backend test suite:

```powershell
python -m pytest -q
```

Run the focused quality and security checks:

```powershell
python -m flake8 server tests --select=E9,F63,F7,F82 --count --statistics
python -m bandit -r server -ll -ii -x server/tests,tests
python -m pip_audit -r requirements.txt
python tests/test_no_emojis.py
```

Run the frontend checks:

```powershell
Set-Location frontend/react-app
npm run build
npm audit --audit-level=high
```

Use `git diff --check` before committing. Tests that contact Stripe, AI
providers, marketplaces, email systems, or a managed database require safe
test credentials and explicit integration-test configuration.

## Deployment

`render.yaml` and the `Dockerfile` provide deployment starting points. Before
using either for a live service:

1. Provision managed PostgreSQL with backups and a tested restore procedure.
2. Store all secrets in the platform secret manager.
3. Set an HTTPS `APP_BASE_URL` and narrow host, origin, and proxy allowlists.
4. Configure Stripe webhook delivery and verify idempotent replay handling.
5. Configure external provider credentials and test each connector against a
   non-production account.
6. Confirm health checks, logs, alerts, resource limits, and scheduler
   ownership for the selected hosting plan.

The default Render blueprint uses the free plan as a development starting
point. It is not a capacity, availability, or compliance guarantee.

## Documentation

- [Security policy](SECURITY.md)
- [Environment template](.env.example)
- [Operator tutorial](docs/TUTORIAL.md)
- [Authentication API](docs/api/auth.md)
- [Generation API](docs/api/generation.md)
- [Billing API](docs/api/billing.md)
- [Inventory API](docs/api/inventory.md)
- [Technical specification](docs/TECHNICAL_SPEC_SHEET.md)
- [Architecture and readiness dossier](docs/BUYER_READY_ARCHITECTURE.md)
- [Test and verification guide](TEST_READY.md)

## License and contribution status

No license or contribution policy is currently declared in this repository.
Obtain project-owner approval before redistributing the code, connecting
production accounts, or publishing a deployment based on this source tree.
