# Security Policy

## Supported versions

Security fixes are applied to the current `main` branch and the latest tagged
release. Deployments should use the latest verified release rather than an
arbitrary working-tree snapshot.

## Reporting a vulnerability

Please report suspected vulnerabilities privately through a GitHub Security
Advisory for this repository. Do not include live API keys, customer data, or
database exports in a report. Include the affected endpoint or file, a minimal
reproduction, impact, and any suggested mitigation.

We will acknowledge a report as soon as practical, investigate it, and provide
an update when the issue is fixed or an alternative mitigation is available.

## Deployment security requirements

- Set `ENVIRONMENT=production` or `staging`.
- Provide unique `JWT_SECRET_KEY`, `INTEGRATION_ENCRYPTION_KEY`, and
  `ADMIN_SECRET` values through the deployment secret manager.
- Use PostgreSQL (or another managed database) for production persistence and
  configure `DATABASE_URL` explicitly.
- Set `ALLOWED_HOSTS`, `ALLOWED_ORIGINS`, and `TRUSTED_PROXIES` to the smallest
  values required by the deployment.
- Keep API documentation disabled unless operators explicitly need it.
