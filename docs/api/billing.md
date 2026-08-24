# Billing and BYOK API

Billing is disabled until Stripe credentials, matching price IDs, and a
webhook signing secret are configured. The prices below are application
registry values, not proof of a live offer or a successful payment.

## Plan catalog

GET /api/plans returns the current application-side catalog. The subscription
registry currently defines:

| Key | Monthly price | Monthly generations | Connectors |
| --- | ---: | ---: | ---: |
| free | 0.00 USD | 5 | 1 |
| boutique | 179.49 USD | 150 | 2 |
| standard | 379.49 USD | 1,000 | 10 |
| megastore | 9,639.63 USD | 2,500 | Application-defined |

The same response includes one-time generation packs. The Stripe account must
contain price objects matching the environment variables in .env.example.

## Subscription checkout

```http
POST /billing/subscribe
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "plan": "standard"
}
```

The response contains a Stripe Checkout URL and session ID:

```json
{
  "checkout_url": "https://checkout.stripe.com/c/pay/<session>",
  "session_id": "<session>"
}
```

The compatibility route /billing/checkout accepts the same subscription
request. A missing Stripe secret or price ID returns a configuration error.

## One-time generation pack

```http
POST /billing/one-time
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "tier": "starter"
}
```

The tier is starter, growth, or scale. Generation credits are granted only
after a verified Stripe checkout.session.completed event.

## Stripe webhook

```http
POST /billing/webhook
Stripe-Signature: t=<timestamp>,v1=<signature>
Content-Type: application/json

<raw Stripe webhook payload>
```

The server verifies the signature before processing and stores event IDs to
prevent duplicate fulfillment. Supported event families include subscription
creation/change/deletion, successful and failed invoices, and completed
checkout sessions.

## BYOK status

```http
GET /api/user/custom-ai-key
Authorization: Bearer <jwt-or-api-key>
```

Response:

```json
{
  "has_custom_key": false,
  "provider": null,
  "unlimited_active": false
}
```

## Save or remove a BYOK key

Only the megastore plan can save a custom OpenAI or Gemini key:

```http
POST /api/user/custom-ai-key
Authorization: Bearer <jwt-or-api-key>
Content-Type: application/json

{
  "provider": "openai",
  "api_key": "sk-proj-<secret>"
}
```

The key is encrypted with INTEGRATION_ENCRYPTION_KEY before persistence and is
never returned. Remove it with:

```http
DELETE /api/user/custom-ai-key
Authorization: Bearer <jwt-or-api-key>
```

For the platform-managed OpenAI provider, configure OPENAI_API_KEY and
OPENAI_MODEL on the server. Never submit that platform key from the browser.
