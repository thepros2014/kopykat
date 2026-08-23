# API Documentation: Authentication & Security

KopyKat supports dual authentication mechanisms:
1. **JWT Bearer Tokens** (for Dashboard and Browser Sessions)
2. **API Keys (`kk_live_...`)** (for Automated Store Webhooks & Developer Integrations)

---

## 1. Register User

```http
POST /auth/register
Content-Type: application/json

{
  "email": "merchant@example.com",
  "password": "StrongPassword123!",
  "full_name": "Jane Merchant"
}
```

### Response (`201 Created`):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "usr_9b1a8f7c-...",
    "email": "merchant@example.com",
    "full_name": "Jane Merchant",
    "plan": "free",
    "generations_remaining": 5,
    "monthly_limit": 5,
    "is_verified": false
  }
}
```

---

## 2. Authenticate User

```http
POST /auth/login
Content-Type: application/json

{
  "email": "merchant@example.com",
  "password": "StrongPassword123!"
}
```

### Response (`200 OK`):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "usr_9b1a8f7c-...",
    "email": "merchant@example.com",
    "plan": "free"
  }
}
```

---

## 3. Create API Key

```http
POST /api/keys
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json

{
  "name": "Shopify Webhook Key"
}
```

### Response (`201 Created`):
```json
{
  "id": "key_3fa85f64-...",
  "name": "Shopify Webhook Key",
  "key_prefix": "kk_live_4b8f",
  "raw_key": "kk_live_4b8fa91c0e227df3881a7b4510",
  "created_at": "2026-08-23T00:00:00Z"
}
```
*Note: The raw key is displayed exactly once upon creation and stored hashed at rest (`SHA-256`).*

---

## 4. Verify Active Session

```http
GET /auth/me
Authorization: Bearer <JWT_TOKEN> or Bearer <API_KEY>
```

### Response (`200 OK`):
```json
{
  "id": "usr_9b1a8f7c-...",
  "email": "merchant@example.com",
  "full_name": "Jane Merchant",
  "plan": "standard",
  "generations_remaining": 980,
  "monthly_limit": 1000,
  "is_verified": true
}
```
