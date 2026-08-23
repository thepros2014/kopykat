# KopyKat — Billing, Pricing & Enterprise BYOK Architecture

This document outlines the Stripe subscription lifecycle, pricing tier parameters, and the Bring-Your-Own-Key (BYOK) architecture for enterprise merchants.

---

## 1. Pricing Tier Matrix

| Tier | Price (USD) | Monthly Quota | Allowed Connectors | Automations Included | BYOK Unlimited AI |
|---|---|---|---|---|---|
| **Test Drive** | $0.00 / mo | 5 Campaigns | 1 | Core Preview | No |
| **Boutique Store** | $179.49 / mo | 150 Campaigns | 2 | 1 (CSV or Auto-Sync) | No |
| **Standard Store** | $379.49 / mo | 1,000 Campaigns | 10 | 2 (CSV + Vision AI) | No |
| **Megastore Infrastructure** | $9,639.63 / mo | 2,500 (Cloud) | Unlimited | All Included | Yes (Unlimited) |

---

## 2. Bring-Your-Own-Key (BYOK) Architecture

Megastore tier customers ($9,639.63/mo) can connect their private OpenAI or Google Gemini developer API keys:
1. **Frontend Input:** Merchant inputs private API key via Dashboard Settings.
2. **Encryption at Rest:** Server encrypts the key using Fernet symmetric encryption with `INTEGRATION_ENCRYPTION_KEY`.
3. **Quota Bypass:** When an active BYOK key is detected on a Megastore account, platform generation limits are bypassed, granting **unlimited campaigns** executed across KopyKat's infrastructure.

---

## 3. Stripe Webhook Lifecycle

The server listens on `POST /billing/webhook` for the following events:
- `customer.subscription.created`: Upgrades user account tier and provisions monthly limits.
- `invoice.payment_succeeded`: Refreshes monthly campaign quota and records a `RevenueRecord`.
- `customer.subscription.deleted`: Downgrades account to `free` tier and clears unused quota.
- `checkout.session.completed`: Handles one-time generation pack purchases (Starter, Growth, Scale).
