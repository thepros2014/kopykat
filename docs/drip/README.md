# KopyKat — Automated Email Conversion Drip Bot

The Email Drip Bot is an autonomous onboarding engine that converts free trial users into paying subscribers through educational, value-first email sequences.

---

## 1. Nurture Schedule & Sequence

- **Schedule:** Daily @ 10:00 UTC via APScheduler.
- **Audience:** All users with `plan == "free"`.

| Trigger Day | Email Goal | Core Value Delivered | Call to Action |
|---|---|---|---|
| **Day 2** | Value & Strategy | Why benefit-driven copy outperforms feature lists; AIDA & PAS frameworks. | Try Ad Copy Generator |
| **Day 4** | Time Savings | Case study on saving 10+ hours per week using Omni-Campaigns. | Generate Landing Page Copy |
| **Day 7** | Plan Upgrade | Quota notice and invitation to upgrade to Boutique or Standard tiers. | Upgrade in Dashboard |

---

## 2. Idempotency & Delivery Guarantees

- **Audit Log:** Every delivery is recorded in `drip_logs` (`user_id`, `step`, `sent_at`).
- **Duplicate Prevention:** The scheduler queries `drip_logs` before dispatching to ensure a user never receives the same drip email twice.
