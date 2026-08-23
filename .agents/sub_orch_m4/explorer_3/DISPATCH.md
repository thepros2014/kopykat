## 2026-08-23T13:30:53Z
Investigate security governance, Pydantic v2 modernization, and M4 test coverage:
1. Examine multi-tenant data scoping across all endpoints (`user_id == user.id`), ensuring no user can access another user's listings, personas, API keys, miners, leads, etc.
2. Examine Fernet encryption for stored credentials and API tokens.
3. Examine bcrypt password hashing and ensure max 72 UTF-8 bytes limit is enforced cleanly.
4. Examine `server/models.py` for Pydantic v2 ConfigDict modernizations (replacing any legacy `class Config`).
5. Examine existing tests and design requirements for `tests/test_frontend_admin_m4.py` covering:
   - Admin MRR metrics endpoint and frontend rendering verification.
   - All 9 dashboard sections rendering and structural presence.
   - Dual-bucket quota reservation and refund mechanisms.
   - Stripe 503 on unconfigured gateway.
   - BYOK Megastore gating.
   - Multi-tenant scoping and Fernet encryption.
   - Flake8 linting and zero-emoji compliance.
6. Write your complete analysis report to `c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m4\explorer_3\handoff.md` and send a summary message.
Do NOT write or modify application code. Only analyze and report.
