# KopyKat operator tutorial

This guide covers a safe local setup and the first authenticated workflow.
For deployment requirements, see the root README and SECURITY.md.

## 1. Install the application

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

For local work, leave ENVIRONMENT as development and use the SQLite default
unless a local PostgreSQL instance is specifically required. Do not reuse
development secrets in staging or production.

## 2. Configure only the services you need

The minimum local setup is a database and an ephemeral application
configuration. AI generation requires GEMINI_API_KEY or another configured
provider. Stripe, email, marketplace, Sentry, and admin features require
their respective settings from .env.example.

Start the service:

```powershell
python -m server.runtime
```

Check:

- GET /health confirms the process is responding.
- GET /ready confirms the application readiness path.
- GET /api/plans returns the configured plan and generation-pack catalog.
- GET /api/docs is available only when ENABLE_API_DOCS is enabled.

## 3. Create and authenticate a test account

Register:

```http
POST /auth/register
Content-Type: application/json

{
  "email": "operator@example.test",
  "password": "Use-a-local-test-password",
  "full_name": "Test Operator"
}
```

The response contains a short-lived bearer token for the local session. Store
it only in the local test environment. In a real deployment, verify email and
password-reset delivery before inviting users.

## 4. Run a first generation

Use the bearer token or a one-time-created API key:

```http
POST /api/generate
Authorization: Bearer <TOKEN>
Content-Type: application/json

{
  "type": "product_description",
  "context": "Insulated stainless-steel bottle for commuters",
  "tone": "professional",
  "variations": 1,
  "max_words": 150
}
```

Generation credits are reserved before the provider call. A provider failure
returns an error and refunds the reserved credits.

## 5. Try a campaign workflow

```http
POST /api/campaign/generate
Authorization: Bearer <TOKEN>
Content-Type: application/json

{
  "keyword": "insulated commuter bottle",
  "product_desc": "A leak-resistant stainless-steel bottle designed for daily travel."
}
```

Review the returned assets before using /api/campaign/push. Pushing requires a
user-owned integration with credentials saved through the integrations API.
Generation does not automatically publish content.

## 6. Connect a platform carefully

Save only the credentials required by the selected integration. Credentials
are encrypted before persistence. Use a test account, verify the provider
scope, and call the connector test route before sending catalog or inventory
updates.

Outbound URLs are validated and private-network destinations are rejected.
Do not use a connector to access local administrative services or metadata
endpoints.

## 7. Operate the scheduled jobs

The application scheduler runs in the web process with these UTC schedules:

| Job | Schedule |
| --- | --- |
| Daily API counter reset | 00:00 |
| Subscription health check | 02:00 |
| Weekly usage cleanup | Sunday 03:00 |
| Daily revenue report | 08:00 |
| Email drip | 10:00 daily |
| Opportunity scout | Every four hours at :15 |
| SEO article generation | Monday, Wednesday, and Friday at 14:00 |

Use one web worker unless scheduled work has been moved to a dedicated
coordination system. Configure email and provider access before enabling jobs.

## 8. Pre-release checklist

- Run the commands in TEST_READY.md.
- Set production secrets through a secret manager.
- Use managed PostgreSQL and test restore procedures.
- Set exact host, origin, and trusted-proxy allowlists.
- Keep interactive API documentation disabled unless required.
- Test Stripe webhook signatures and replay behavior.
- Test every enabled connector against non-production accounts.
- Confirm logs, alerts, support ownership, and rollback procedures.
