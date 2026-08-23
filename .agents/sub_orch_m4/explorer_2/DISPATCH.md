## 2026-08-23T13:30:53Z

You are Explorer 2 for Milestone 4 (Financial Invariants & Quota Ledger).
Working directory: c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m4\explorer_2\
Original Request Path: c:\Users\plumb\Desktop\claude-project\.agents\ORIGINAL_REQUEST.md
PROJECT.md Path: c:\Users\plumb\Desktop\claude-project\PROJECT.md
SCOPE.md Path: c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m4\SCOPE.md

Your Task:
Investigate the backend financial invariants, quota management, and tier gating in `server/main.py`, `server/models.py`, `server/auth.py`, `server/database.py`, etc.:
1. Inspect `reserve_user_generations` and `refund_user_generations`:
   - Dual-bucket prioritization: monthly quota used first, then purchased quota.
   - Atomic refund on upstream errors / generation failures across all generation routes (AI, listings, UGC, miners, etc.).
2. Inspect Stripe checkout / webhook routes and verify HTTP 503 behavior when Stripe keys/gateway are unconfigured.
3. Inspect BYOK (Bring Your Own Key) custom AI keys endpoints and verify strict tier gating (restricted strictly to Megastore tier users).
4. Identify all routes and handlers that require updates, error handling improvements, or invariants enforcement in `server/main.py`.
5. Write your complete analysis report to `c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m4\explorer_2\handoff.md` and send a summary message.
Do NOT write or modify application code. Only analyze and report.
