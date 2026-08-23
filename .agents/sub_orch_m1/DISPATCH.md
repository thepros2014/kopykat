## 2026-08-23T10:17:39Z
You are the Sub-Orchestrator for Milestone 1 (Multi-Modal Campaign & Platform Schemas).
Your Working Directory: c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m1
Original Request Path: c:\Users\plumb\Desktop\claude-project\.agents\ORIGINAL_REQUEST.md
PROJECT.md Path: c:\Users\plumb\Desktop\claude-project\PROJECT.md
Project Root: c:\Users\plumb\Desktop\claude-project

Scope: Milestone 1 (Features F1, F2, F3, F4, F5, F6)
Write Ownership: `server/ai_engine.py`, `server/campaigns.py`, `server/models.py`, `tests/test_marketplace_schemas.py`, `tests/test_addons_monetization.py`.

Tasks:
1. Read `ORIGINAL_REQUEST.md` and `PROJECT.md § Milestones / M1`.
2. Implement and verify the multi-modal campaign & platform listing optimizer pipeline:
   - Extend `MarketplaceOptimizeRequest` in `server/models.py` with pattern `^(amazon|shopify|etsy|tiktok|tiktok_shop|ebay)$`.
   - In `server/ai_engine.py`: implement complete structured schema generators, formatting rules, character/byte constraints, and deterministic offline fallbacks for:
     - Amazon: Title < 200 chars, 5 bullet points, backend keywords < 249 bytes, compliance score.
     - Shopify: Title < 70 chars, meta description < 155 chars, 4 bullet points, DTC structured HTML description, compliance score.
     - Etsy: Title < 140 chars, 13 long-tail tags (< 20 chars each), 3-4 bullets, warm artisan description, compliance score.
     - TikTok Shop: Title < 100 chars (Viral hook + Product + Benefit), 3-5 punchy bullets, 3 video hooks/scripts, 5-8 trending hashtags, mobile description, compliance score.
     - eBay: Title < 80 chars, subtitle < 55 chars, item specifics dict (Brand, MPN, Material, etc.), 3-4 bullets, HTML listing template with policies, compliance score.
   - Verify multi-modal vision pipeline in `server/campaigns.py` and `POST /api/campaign/generate-vision`.
3. Dispatch Worker -> Reviewer -> Challenger -> Auditor cycle to implement and rigorously verify M1.
   MANDATORY INTEGRITY WARNING: DO NOT CHEAT. All implementations must be genuine. Zero-emoji policy strictly enforced.
4. Verify: `python -m pytest tests/ -v`, `python -m flake8 server --count --select=E9,F63,F7,F82`, and `python tests/test_no_emojis.py`.
5. Write `handoff.md` and report back to parent.
