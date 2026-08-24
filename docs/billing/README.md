# Billing and provider configuration

## Application plan registry

The application-side registry currently contains:

| Plan | Monthly price | Monthly generations | Notes |
| --- | ---: | ---: | --- |
| Test Drive | 0.00 USD | 5 | One connector |
| Boutique Store | 179.49 USD | 150 | Two connectors |
| Standard Store | 379.49 USD | 1,000 | Ten connectors |
| Megastore Infrastructure | 9,639.63 USD | 2,500 | BYOK entitlement available |

These are source configuration values. They are not a statement that the
plans are publicly offered, purchased, or suitable for a specific customer.
The current plan catalog is available from GET /api/plans.

## Stripe lifecycle

1. An authenticated user requests checkout.
2. The server creates a Stripe Checkout session using a configured price ID.
3. Stripe sends a signed webhook to POST /billing/webhook.
4. The server verifies and deduplicates the event.
5. Subscription, generation, payment, and entitlement records are updated.

Required environment variables include STRIPE_SECRET_KEY,
STRIPE_WEBHOOK_SECRET, the recurring plan price IDs, and the generation-pack
price IDs. Missing values return a configuration error; the application does
not fabricate a successful checkout.

## Generation packs and add-ons

One-time packs grant purchased generations only after verified checkout
fulfillment. Add-ons create or activate user entitlements according to the
registry. Review the registry in server/billing.py when changing pricing or
entitlement behavior.

## OpenAI and Gemini

The managed AI provider is configured server-side:

- OpenAI: OPENAI_API_KEY, OPENAI_MODEL, and AI_PROVIDER=openai.
- Gemini: GEMINI_API_KEY, GEMINI_MODEL, and AI_PROVIDER=gemini.

The OpenAI adapter uses the Responses API and does not store generated
responses by default. Provider credentials must never be shipped to browser
clients.

Megastore users can save a provider-specific BYOK key through the authenticated
BYOK routes. The key is encrypted with INTEGRATION_ENCRYPTION_KEY before it is
persisted and is never returned by the API.

## Release controls

Use Stripe test mode first, verify replay behavior, record the webhook event
types used by the deployment, and review payment and refund handling before
enabling live prices. Administrative revenue metrics reflect the current
database only and do not establish customer or revenue status.
