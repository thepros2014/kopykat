# Authentication API

All examples are illustrative. Replace tokens and identifiers with values
from the current environment. Never place real credentials in source control,
tickets, screenshots, or documentation.

## Authentication methods

- Browser sessions use JWT bearer tokens.
- Programmatic routes that accept API keys use a bearer value beginning with
  kk_live_.
- The route dependency determines which credential type is accepted.

## Register

```http
POST /auth/register
Content-Type: application/json

{
  "email": "operator@example.test",
  "password": "A-local-test-password",
  "full_name": "Test Operator"
}
```

The response is a TokenResponse:

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "plan": "free",
  "generations": 5
}
```

Registration sends verification mail only when the email service is
configured. Do not treat a local registration as a verified production
identity.

## Login

```http
POST /auth/login
Content-Type: application/json

{
  "email": "operator@example.test",
  "password": "A-local-test-password"
}
```

Use the returned access token as:

```http
Authorization: Bearer <jwt>
```

## Current user

```http
GET /auth/me
Authorization: Bearer <jwt>
```

Example response:

```json
{
  "id": "user-id",
  "email": "operator@example.test",
  "full_name": "Test Operator",
  "plan": "free",
  "generations": 5,
  "monthly_limit": 5,
  "created_at": "2026-01-01T00:00:00"
}
```

## API keys

Create a key with a JWT:

```http
POST /api/keys
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "name": "Local integration key"
}
```

The raw key is returned only in the creation response:

```json
{
  "id": "key-id",
  "key_prefix": "kk_live_abcd",
  "name": "Local integration key",
  "is_active": true,
  "last_used": null,
  "requests_today": 0,
  "created_at": "2026-01-01T00:00:00",
  "raw_key": "kk_live_<secret>"
}
```

Store the raw key in a secret manager immediately. Later list operations
return metadata only:

```http
GET /api/keys
Authorization: Bearer <jwt>
```

Revoke a key:

```http
DELETE /api/keys/{key_id}
Authorization: Bearer <jwt>
```

## Verification and password reset

- POST /auth/request-verification accepts an email.
- POST /auth/verify-email accepts a verification token.
- POST /auth/request-password-reset accepts an email.
- POST /auth/reset-password accepts a reset token and a new password.

Tokens expire and should be treated as secrets. Passwords are bounded by the
server and must not be logged.

## Operational notes

Use HTTPS in staging and production. Rotate JWT, admin, integration, and
provider secrets through the deployment secret manager. A password reset or
authentication-version change invalidates older JWTs.
