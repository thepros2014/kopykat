# KopyKat test infrastructure

## Test philosophy

The suite combines unit tests, integration-style tests, boundary checks,
pairwise workflows, adversarial cases, and browser-source checks. The goal is
to verify observable behavior and security invariants without making the
tests depend unnecessarily on private implementation details.

Tests should be deterministic, isolated, and safe to run without live
customer data. Provider calls should be mocked or directed to explicit
test-mode accounts.

## Test organization

| Group | Examples | Focus |
| --- | --- | --- |
| Core behavior | test_campaigns.py, test_marketplace_schemas.py | Generation and response contracts |
| Authentication | test_auth_verification.py | Passwords, tokens, API keys, reset flows |
| Billing | test_billing_webhook.py, test_byok_pricing.py | Stripe events, entitlements, quota grants |
| Connectors | test_connectors.py, test_ssrf_async.py | Outbound safety and platform adapters |
| Inventory | test_inventory.py | Stock updates, fanout, reconciliation, replay handling |
| Growth | test_growth_engines.py, test_reddit_scout.py, test_seo_marketing.py | SEO, review, drip, and opportunity workflows |
| Hardening | test_adversarial_hardening.py, test_tier5_adversarial_hardening.py, test_production_hardening.py | Abuse cases and strict configuration |
| Frontend | test_frontend_admin_m4.py, test_no_emojis.py | Safe rendering and repository-wide output policy |
| End-to-end | test_e2e_tiers.py, test_e2e_enterprise.py | Cross-feature behavior |

The exact number of tests changes as the repository evolves. Use pytest
output from the current checkout as the source of truth.

## Standard commands

From the repository root:

```powershell
python -m pytest -q
python -m compileall -q server tests
python -m flake8 server tests --select=E9,F63,F7,F82 --count --statistics
python -m bandit -r server -ll -ii -x server/tests,tests
python -m pip_audit -r requirements.txt
python tests/test_no_emojis.py
```

For the React application:

```powershell
Set-Location frontend/react-app
npm ci
npm run build
npm audit --audit-level=high
```

## Invariants under test

- Users cannot read or mutate another tenant's records.
- Passwords and secrets are bounded, hashed or encrypted, and never returned
  after the one-time API-key creation response.
- Password resets and authentication-version changes invalidate older JWTs.
- Generation credits are reserved before expensive provider calls and
  refunded when the call fails.
- Stripe and inventory event IDs prevent duplicate fulfillment or stock
  changes when a provider retries a webhook.
- Outbound connector requests reject local, private, link-local, metadata, and
  otherwise unsafe destinations; redirects and oversized responses are bounded.
- HTML content is sanitized before persistence or rendered through safe DOM
  operations.
- Strict environments do not start with placeholder secrets, SQLite, or an
  insecure public base URL.
- Public and administrative metrics are calculated from persisted instance
  data rather than hard-coded marketing values.

## Test data and isolation

- Use temporary databases and unique test users.
- Clear environment variables between tests that exercise configuration
  import-time behavior.
- Do not use `.env`, local database files, backup codes, or copied production
  exports as fixtures.
- Keep provider credentials in CI secret stores and use revocable test keys.
- Verify that logs and assertion messages do not print tokens or credentials.

## Release gates

A release candidate should have:

1. A clean pytest run and a reviewed warning list.
2. A successful frontend production build.
3. No high-severity dependency findings.
4. Reviewed Bandit output and no unapproved exceptions.
5. A successful strict-configuration startup check.
6. Integration tests for every enabled provider.
7. Database backup/restore evidence and a rollback procedure.

Passing this suite is necessary for a controlled release, but it does not
establish uptime, capacity, compliance, or provider certification.
