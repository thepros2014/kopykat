## 2026-08-23T10:23:34Z
You are Worker 1 for Milestone 1 (Multi-Modal Campaign & Platform Schemas).
Your working directory: c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m1\worker_1

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Zero-Emoji Policy: STRICTLY ENFORCED across all code, docstrings, prompts, templates, and fallbacks.

Read these files before starting work:
- c:\Users\plumb\Desktop\claude-project\.agents\ORIGINAL_REQUEST.md
- c:\Users\plumb\Desktop\claude-project\PROJECT.md
- c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m1\SCOPE.md
- c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m1\explorer_1\analysis.md
- c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m1\explorer_2\analysis.md
- c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m1\spec_miner_1\spec_report.md

Your tasks:
1. `server/models.py`:
   - Update `MarketplaceOptimizeRequest.platform`: `Field(pattern="^(amazon|shopify|etsy|tiktok|tiktok_shop|ebay)$")`
   - Update `MarketplaceOptimizeResponse`: add `short_hooks: list[str] = []`, `hashtags: list[str] = []`, `sub_title: Optional[str] = None`, `item_specifics: Optional[dict] = None`.
2. `server/ai_engine.py`:
   - In `optimize_marketplace_listing`:
     - Update prompt construction for `amazon`, `shopify`, `etsy`, `tiktok` / `tiktok_shop`, and `ebay`.
     - Update deterministic offline fallback for all platforms:
       - Amazon: Title < 200 chars, 5 bullet points with capitalized hooks, backend_search_terms < 249 bytes (UTF-8, space-separated), compliance_score 95.
       - Shopify: Title < 70 chars, meta_description < 155 chars, 4 bullet points, DTC structured HTML description with H2 headings, compliance_score 98.
       - Etsy: Title < 140 chars, 13 long-tail tags (< 20 chars each), 3-4 bullets, warm artisan description, compliance_score 96.
       - TikTok Shop: Title < 100 chars (Viral hook + Product + Benefit), 3-5 punchy bullets, 3 video hooks/scripts (`short_hooks`), 5-8 trending hashtags (`hashtags`), mobile description, compliance_score 96.
       - eBay: Title < 80 chars, subtitle (`sub_title`) < 55 chars, `item_specifics` dict (Brand, MPN, Condition, Material, Type), 3-4 bullets, HTML listing template with policies, compliance_score 95.
3. `server/campaigns.py`:
   - Implement `_generate_fallback_vision_campaign` in `generate_omni_campaign_from_image` when AI provider is unconfigured or fails.
   - Enhance `_extract_clean_json` with regex fallback (`re.search(r'\{.*\}', clean_text, re.DOTALL)`).
4. `server/main.py`:
   - In `/api/optimizer/marketplace-listing`: construct `MarketplaceOptimizeResponse` with `short_hooks`, `hashtags`, `sub_title`, `item_specifics`.
   - In `/api/campaign/generate-vision`: use `reserve_user_generations(user.id, 1, db)` and `refund_user_generations(user.id, monthly_used, purchased_used, db)` instead of raw SQL update / transaction rollback bug.
5. Create comprehensive unit tests in `tests/test_marketplace_schemas.py` testing:
   - All 5 platform schemas, character/byte caps, fallback outputs, compliance scores >= 90.
   - Platform enum validation (valid platforms pass, invalid platforms return 422).
   - Dual-bucket reservation/refund behavior on `/api/campaign/generate-vision`.
   - Zero emojis in all outputs.
6. Verify your implementation by running:
   - `python -m pytest tests/ -v`
   - `python -m flake8 server --count --select=E9,F63,F7,F82`
   - `python tests/test_no_emojis.py`
7. Write your handoff report to `c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m1\worker_1\handoff.md` and send a completion message back.
