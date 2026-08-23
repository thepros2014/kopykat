# BRIEFING — 2026-08-23T13:35:00Z

## Mission
Investigate backend financial invariants, quota ledger, reservation/refund flows, Stripe failure modes, and BYOK tier gating for Milestone 4.

## 🔒 My Identity
- Archetype: Explorer
- Roles: Read-only investigation, codebase analysis, synthesis & reporting
- Working directory: c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m4\explorer_2
- Original parent: 39e8adc7-6ac4-46f0-81ee-c8b673ea7ca6
- Milestone: Milestone 4 (Financial Invariants & Quota Ledger)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement or modify application code
- All findings must reference exact file paths, line numbers, and quotes
- Self-contained 5-component handoff report
- Deliver findings back to orchestrator via send_message and handoff.md

## Current Parent
- Conversation ID: 39e8adc7-6ac4-46f0-81ee-c8b673ea7ca6
- Updated: 2026-08-23T13:35:00Z

## Investigation State
- **Explored paths**: `server/main.py`, `server/models.py`, `server/auth.py`, `server/database.py`, `server/billing.py`, `server/ai_engine.py`, `server/inventory.py`, `tests/`
- **Key findings**:
  1. `reserve_user_generations` / `refund_user_generations` properly implements dual-bucket prioritization (monthly before purchased) and row locking with `with_for_update()`.
  2. Identified defect in `/api/competitor/mine-reviews` (`server/main.py:848-853, 884-887`): uses direct raw SQL balance modification rather than `reserve_user_generations` / `refund_user_generations`.
  3. Identified Stripe 503 edge case in `create_subscription_checkout` and `create_one_time_checkout` in `server/billing.py` where existing `stripe_customer_id` skips checking `stripe.api_key`.
  4. Verified BYOK endpoints (`/api/user/custom-ai-key`) strictly enforce Megastore tier gating (HTTP 403) and encrypt API keys using Fernet.
  5. Identified Pydantic v2 `ConfigDict` modernization for `UserProfile` and `APIKeyResponse` in `server/models.py`.
- **Unexplored areas**: None for M4 backend financial invariants.

## Key Decisions Made
- Fully documented all observations, logic chains, caveats, actionable conclusions, and test verification methods in `handoff.md`.

## Artifact Index
- `DISPATCH.md` — Inbound instructions
- `BRIEFING.md` — Working memory & context index
- `progress.md` — Liveness & step heartbeat
- `handoff.md` — Final 5-component handoff report
