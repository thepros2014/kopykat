# KopyKat verification guide

This document describes the repeatable checks for the repository. Test results
are environment- and dependency-dependent; always trust the current command
output over a historical count in a document.

## Backend tests

Run the complete suite from the repository root:

```powershell
python -m pytest -q
```

Useful focused runs:

```powershell
python -m pytest tests/test_auth_verification.py tests/test_security_headers.py -q
python -m pytest tests/test_billing_webhook.py tests/test_byok_pricing.py -q
python -m pytest tests/test_connectors.py tests/test_ssrf_async.py tests/test_platform_hardening.py -q
python -m pytest tests/test_inventory.py tests/test_adversarial_hardening.py -q
python -m pytest tests/test_production_hardening.py -q
```

## Quality and security checks

```powershell
python -m compileall -q server tests
python -m flake8 server tests --select=E9,F63,F7,F82 --count --statistics
python -m bandit -r server -ll -ii -x server/tests,tests
python -m pip_audit -r requirements.txt
python tests/test_no_emojis.py
git diff --check
```

The focused Flake8 selection catches syntax and undefined-name failures. It is
not a replacement for a project-wide style policy. Review Bandit low-severity
findings and any environment-specific warnings instead of treating a clean
exit code as a complete security audit.

## Frontend checks

```powershell
Set-Location frontend/react-app
npm ci
npm run build
npm audit --audit-level=high
```

The build runs TypeScript checking before Vite bundling. npm audit should be
run against the lockfile that will be deployed.

## Coverage areas

| Area | Representative checks |
| --- | --- |
| Authentication | Registration, login, token revocation, API keys, password reset |
| Tenant isolation | User-scoped records, connector credentials, inventory, personas |
| Quotas | Reservation order, exhaustion, refund behavior, concurrency boundaries |
| Billing | Checkout configuration, signed webhooks, duplicate event handling |
| AI workflows | Managed-provider adapter, fallback behavior, image input limits |
| Connectors | URL validation, private-network blocking, response limits, redirects |
| Inventory | SKU updates, fanout, reconciliation, event replay handling |
| Generated content | HTML sanitization, safe frontend rendering, bounded fields |
| Operations | Health/readiness, production configuration, request limits, headers |
| Frontend | DOM-safe rendering, truthful empty states, React production build |

## External integration testing

The default test suite uses local substitutes and mocks where appropriate.
Before enabling a provider in production, run a controlled integration test
for each of the following:

- PostgreSQL connection, migrations, backup, and restore.
- Stripe test-mode checkout and every webhook event used by the deployment.
- AI provider authentication, model availability, timeouts, and quota errors.
- Marketplace credentials, catalog reads, inventory writes, and rate limits.
- Email delivery, unsubscribe behavior, and failure handling.
- Sentry or another monitoring destination, if configured.

Never place live credentials in tests, fixtures, logs, screenshots, or
committed environment files.

## Release evidence

For a release candidate, retain:

1. The commit identifier and dependency lockfiles.
2. Test and build output, including warnings that remain.
3. Dependency-audit results and any accepted exceptions.
4. Database migration and restore evidence.
5. Provider integration-test results.
6. A review of environment variables, hosts, origins, proxies, and secrets.
7. A rollback plan and an owner for incident response.

## What these checks do not prove

Passing local tests does not prove that a deployment has adequate capacity,
availability, backups, legal compliance, provider approval, customer support,
or production data. Those are separate release decisions.
