# Handoff Report — Backend Architecture & Connectors Survey

**Date:** 2026-08-23  
**Author:** Explorer 1 (Backend & Connectors Survey)  
**Recipient:** Orchestrator (`fa22ff25-342d-4873-9c36-b1fd82bb7712`)  
**Artifacts Generated:**  
- `c:\Users\plumb\Desktop\claude-project\.agents\explorer_survey_1\analysis.md`
- `c:\Users\plumb\Desktop\claude-project\.agents\explorer_survey_1\handoff.md`
- `c:\Users\plumb\Desktop\claude-project\.agents\explorer_survey_1\progress.md`
- `c:\Users\plumb\Desktop\claude-project\.agents\explorer_survey_1\BRIEFING.md`

---

## 1. Observation

Direct observations from codebase inspection, database models, and test execution:

1. **Framework & Dependencies (`requirements.txt:1-21`):**
   - Framework: `fastapi>=0.115.0`, `uvicorn[standard]>=0.30.0`, `sqlalchemy>=2.0.30`.
   - Security/Auth/Billing: `stripe>=9.6.0`, `PyJWT[crypto]>=2.9.0`, `bcrypt>=4.0.0`, `cryptography>=44.0.1`, `bleach>=6.4.0`, `slowapi>=0.1.10`.
   - AI/Async/Background: `openai>=1.35.0`, `google-generativeai>=0.7.2`, `httpx>=0.27.0`, `apscheduler>=3.10.4`, `requests>=2.32.3`.

2. **Test Suite Baseline Execution:**
   - Tool Command: `python -m pytest tests/ -v`
   - Output: `65 passed, 7 warnings in 15.07s` (Exited with code 0).
   - Tool Command: `python -m flake8 server --count --select=E9,F63,F7,F82`
   - Output: `0` (Exited with code 0).
   - Tool Command: `python -m pytest tests/test_no_emojis.py -v`
   - Output: `1 passed in 0.05s` (Exited with code 0).

3. **Database Models & ORM (`server/database.py:22-293`):**
   - 21 models defined using SQLAlchemy 2.0 `DeclarativeBase`: `User`, `APIKey`, `Subscription`, `VerificationToken`, `UserIntegration`, `Campaign`, `PushJob`, `UsageRecord`, `RevenueRecord`, `StripeEvent`, `CustomConnector`, `ConnectorAuditLog`, `BlogPost`, `DripLog`, `CompetitorAudit`, `InventoryItem`, `InventoryWebhookEvent`, `InventorySyncLog`, `CustomerReview`, `PriceMarginItem`, `UserEntitlement`, `BrandPersona`, `OpportunityLog`.
   - `InventoryWebhookEvent` enforces idempotency via `UniqueConstraint("platform", "event_id", name="uq_platform_event_id")` at line 215.
   - `UserIntegration` enforces unique tenant connection per platform via `UniqueConstraint("user_id", "platform", name="uq_user_platform")` at line 81.

4. **Connector Implementations (`server/connector_engine.py`, `server/connector_registry.py`, `server/integrations.py`):**
   - `server/connector_engine.py:47-68` fetches OpenAPI docs synchronously via `requests.get()`.
   - `server/connector_registry.py:57-83` executes HTTP operations synchronously via `requests.request()`.
   - `server/integrations.py:110-124` contains stub methods `push_to_amazon`, `push_to_ebay`, `push_to_walmart`, `push_to_temu` which raise `NotImplementedError` via `_unsupported_marketplace()`.
   - `server/shopify_import.py:24-88` implements direct Shopify catalog import via `httpx.AsyncClient`.

5. **Pessimistic Locking & Quota Accounting (`server/main.py:320-366`, `server/inventory.py:51-58`):**
   - `reserve_user_generations()` in `server/main.py:327-328` and `sync_inventory_across_platforms()` in `server/inventory.py:55-56` apply `query.with_for_update()` on non-SQLite database dialects.
   - Atomic SQL fallback is utilized in `server/main.py:619-624` and `852-857`.

6. **SSRF & DNS Rebinding Protections (`server/connector_engine.py:27-45`, `server/integrations.py:11-34`):**
   - `validate_public_url` resolves hostname via `socket.getaddrinfo()` and rejects private/loopback/link-local/multicast IP addresses.
   - However, outbound requests are made via `requests` which performs a secondary DNS resolution at request time, exposing a Time-of-Check to Time-of-Use (TOCTOU) DNS rebinding vulnerability, and blocking the async event loop during execution.

---

## 2. Logic Chain

1. **Premise 1 (Observed in Observation 2):** The existing codebase has a clean baseline (65 tests passing, 0 flake8 errors, 0 emojis). Any modifications must preserve these guarantees.
2. **Premise 2 (Observed in Observation 4 & 6):** The existing connector discovery (`connector_engine.py`) and execution runtime (`connector_registry.py`) use synchronous `requests` calls and perform separate pre-flight DNS validation.
3. **Inference 1:** Because `requests` re-resolves the domain name upon connecting, an attacker operating a DNS server can return a safe public IP during `validate_public_url()` and a restricted private/loopback IP (e.g. `127.0.0.1`, `169.254.169.254`) on the subsequent connection. Additionally, synchronous I/O blocks the Uvicorn/FastAPI event loop.
4. **Inference 2:** To satisfy Requirement #2 ("non-blocking async HTTP with strict SSRF and DNS rebinding protections"), outbound HTTP execution must migrate to an async client (`httpx.AsyncClient` or custom transport) that pins the pre-validated IP directly to the socket connection while preserving the Host/SNI header for TLS certificate validation.
5. **Premise 3 (Observed in Observation 3 & 4):** Amazon, eBay, Etsy, and TikTok Shop connectors currently lack full bidirectional sync clients in `server/integrations.py`.
6. **Inference 3:** A unified `PlatformConnector` protocol must be established, and dedicated connector adapters must be implemented for Amazon, Shopify, Etsy, TikTok Shop, and eBay to fulfill Requirement #2.
7. **Premise 4 (Observed in Observation 3 & 5):** `InventoryWebhookEvent` and `reserve_user_generations` have established the architectural pattern for `(platform, event_id)` idempotency and pessimistic locking (`with_for_update()`).
8. **Inference 4:** This pattern should be standardized across all webhook entry points and quota-consuming operations.

---

## 3. Caveats

- **Network Mode:** The local test suite executes in a self-contained mock environment. Outbound requests in unit tests must remain mocked (e.g. via `monkeypatch` or `unittest.mock`) to prevent external network flakiness.
- **SQLite vs PostgreSQL Locking:** SQLite does not support `SELECT ... FOR UPDATE` row locks; SQLite locks at the database file level. The codebase conditionally checks `if db.bind.dialect.name != "sqlite": query = query.with_for_update()`, which provides row-level pessimistic locking in PostgreSQL production deployments while maintaining local SQLite developer ergonomics.
- **Scope Limit:** Explorer 1 is a read-only investigation role. No source code modifications in `server/` or `tests/` were written during this turn; all findings and designs are delivered via reports in `.agents/explorer_survey_1/`.

---

## 4. Conclusion

1. **Codebase Health:** The KopyKat backend is well-structured, modular, and possesses a robust test suite (65 passing tests, 0 flake8 errors, clean security headers, strict zero-emoji enforcement).
2. **Gap Closure for Requirement #2:**
   - **Autonomous Connectors:** Implement standardized adapters for Amazon, Shopify, Etsy, TikTok Shop, and eBay.
   - **Async HTTP & DNS Rebinding:** Build `SafeAsyncHTTPClient` using `httpx.AsyncClient` with custom socket-level IP binding to eliminate TOCTOU DNS rebinding vulnerabilities and event loop blocking.
   - **Real-Time Sync Engine:** Expand `SUPPORTED_INVENTORY_PLATFORMS` and implement async fanout orchestration with loop prevention and drift reconciliation.
   - **Idempotency & Pessimistic Locking:** Ensure uniform `(platform, event_id)` deduplication and atomic credit reservation across all endpoints.
3. **Execution Ready:** Detailed designs, contracts, and module targets are fully documented in `analysis.md`.

---

## 5. Verification Method

To independently verify all findings and test suites:

1. **Run full pytest test suite:**
   ```powershell
   python -m pytest tests/ -v
   ```
   *Expected Result:* 65 passed in ~15s, 0 failures.

2. **Verify Flake8 linter compliance:**
   ```powershell
   python -m flake8 server --count --select=E9,F63,F7,F82
   ```
   *Expected Result:* 0 errors.

3. **Verify zero-emoji policy compliance:**
   ```powershell
   python -m pytest tests/test_no_emojis.py -v
   ```
   *Expected Result:* 1 passed in ~0.05s.

4. **Inspect Analysis Report:**
   - File: `c:\Users\plumb\Desktop\claude-project\.agents\explorer_survey_1\analysis.md`
   - File: `c:\Users\plumb\Desktop\claude-project\.agents\explorer_survey_1\handoff.md`

5. **Invalidation Conditions:**
   - Any failing pytest test or flake8 syntax/name error.
   - Introduction of synchronous blocking HTTP in async route handlers.
   - Incomplete URL validation allowing private IP ranges or DNS rebinding.
