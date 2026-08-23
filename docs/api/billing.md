# API Documentation: Billing, Subscriptions & BYOK

KopyKat integrates with Stripe for automated subscription billing, one-time generation top-ups, and encrypted Bring-Your-Own-Key (BYOK) configurations.

---

## 1. Plan Registry

| Plan Key | Name | Price (USD) | Included Campaigns | Connectors | Automations | BYOK Unlimited |
|---|---|---|---|---|---|---|
| `free` | Test Drive | $0.00 / mo | 5 | 1 | 1 | No |
| `boutique` | Boutique Store | $179.49 / mo | 150 | 2 | 1 | No |
| `standard` | Standard Store | $379.49 / mo | 1,000 | 10 | 2 | No |
| `megastore` | Megastore Infrastructure | $9,639.63 / mo | 2,500 | Unlimited | Unlimited | Yes |

---

## 2. Start Subscription Checkout

```http
POST /billing/subscribe
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json

{
  "plan": "standard"
}
```

### Response (`200 OK`):
```json
{
  "checkout_url": "https://checkout.stripe.com/c/pay/cs_live_a1b2c3...",
  "session_id": "cs_live_a1b2c3..."
}
```

---

## 3. Stripe Webhook Listener

```http
POST /billing/webhook
Stripe-Signature: t=1614000000,v1=...
Content-Type: application/json

<Raw Stripe Webhook Payload>
```
*Handled Events:* `checkout.session.completed`, `invoice.payment_succeeded`, `customer.subscription.deleted`.

---

## 4. Configure Megastore BYOK (Bring Your Own Key)

*Restricted to accounts on the `megastore` tier.*

```http
POST /api/user/custom-ai-key
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json

{
  "provider": "openai",
  "api_key": "sk-proj-0123456789abcdef..."
}
```

### Response (`200 OK`):
```json
{
  "success": true,
  "message": "Custom AI API Key securely saved. Unlimited generations via your infrastructure are now active."
}
```
*Security: Key is encrypted via Fernet using `INTEGRATION_ENCRYPTION_KEY` before persistent storage.*

---

## 5. Check BYOK Status

```http
GET /api/user/custom-ai-key
Authorization: Bearer <JWT_TOKEN>
```

### Response (`200 OK`):
```json
{
  "has_custom_key": true,
  "provider": "openai",
  "unlimited_active": true
}
```
