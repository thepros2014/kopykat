## 2026-08-23T10:18:12Z
You are Explorer 2 for Milestone 2 (Autonomous Connectors, Real-Time Sync & Async SSRF Defense).
Your working directory: c:\Users\plumb\Desktop\claude-project\.agents\explorer_m2_2\
Original Request: c:\Users\plumb\Desktop\claude-project\.agents\ORIGINAL_REQUEST.md
PROJECT.md: c:\Users\plumb\Desktop\claude-project\PROJECT.md
SCOPE.md: c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m2\SCOPE.md
Project Root: c:\Users\plumb\Desktop\claude-project

Tasks:
1. Read ORIGINAL_REQUEST.md, PROJECT.md, and SCOPE.md.
2. Investigate `server/integrations.py`, existing connectors, and connector interfaces across the codebase.
3. Design the standardized `PlatformConnector` architecture and implementations for:
   - Amazon (SP-API / mock API integration with auth/signatures, fetch_catalog, push_product, update_stock, verify_webhook)
   - Shopify (Admin API integration, GraphQL/REST, fetch_catalog, push_product, update_stock, HMAC SHA256 webhook verification)
   - Etsy (v3 API integration, OAuth/API key, fetch_catalog, push_product, update_stock, webhook verification)
   - TikTok Shop (Open API integration, signature/token, fetch_catalog, push_product, update_stock, webhook verification)
   - eBay (Fulfillment / Inventory API, OAuth, fetch_catalog, push_product, update_stock, webhook verification)
4. Check error handling, rate limiting handling, authentication credential handling (Fernet decryption integration if applicable), and compatibility with `SafeAsyncHTTPClient`.
5. Check zero-emoji invariant and flake8 compliance requirements.
6. Write a detailed analysis report to `c:\Users\plumb\Desktop\claude-project\.agents\explorer_m2_2\analysis.md` and handoff report `c:\Users\plumb\Desktop\claude-project\.agents\explorer_m2_2\handoff.md`.
7. Send a message to parent with the summary and path to your handoff.
