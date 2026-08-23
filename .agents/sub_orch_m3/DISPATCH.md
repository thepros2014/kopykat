# DISPATCH

## 2026-08-23T10:17:39Z
You are the Sub-Orchestrator for Milestone 3 (Automated Growth Engine, Lead Generation & Telemetry).
Your Working Directory: c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m3
Original Request Path: c:\Users\plumb\Desktop\claude-project\.agents\ORIGINAL_REQUEST.md
PROJECT.md Path: c:\Users\plumb\Desktop\claude-project\PROJECT.md
Project Root: c:\Users\plumb\Desktop\claude-project

Scope: Milestone 3 (Features F11, F12, F13, F14)
Write Ownership: `server/marketing.py`, `server/reviews_ugc.py`, `server/pricing_monitor.py`, `tests/test_growth_engines.py`, `tests/test_ugc_reviews.py`, `tests/test_reddit_scout.py`.

Tasks:
1. Read `ORIGINAL_REQUEST.md` and `PROJECT.md § Milestones / M3`.
2. Implement and verify the Automated Growth Engine, Lead Generation & Telemetry:
   - SEO Blog Generation Engine in `server/marketing.py`: keyword library, sanitized HTML generation with bleach, sitemap.xml, robots.txt, and ping-index notification.
   - Review Sentiment & UGC Drips in `server/reviews_ugc.py`: 3-step post-purchase drip templates, positive/neutral/negative sentiment classifier, automated draft resolution replies.
   - Lead Gen & Competitor Review Mining: Reddit opportunity scout with 75-99 intent scoring and AI reply generation in `server/marketing.py`; 1-star competitor flaw miner in `server/ai_engine.py`.
   - Admin Revenue & MRR Telemetry: Ensure `/admin/mrr-metrics` accurately computes MRR, ARR, subscriber tier breakdown, lifetime revenue, and software asset valuation score.
3. Dispatch Worker -> Reviewer -> Challenger -> Auditor cycle to implement and rigorously verify M3.
   MANDATORY INTEGRITY WARNING: DO NOT CHEAT. All implementations must be genuine. Zero-emoji policy strictly enforced.
4. Verify: `python -m pytest tests/ -v`, `python -m flake8 server --count --select=E9,F63,F7,F82`, and `python tests/test_no_emojis.py`.
5. Write `handoff.md` and report back to parent.
