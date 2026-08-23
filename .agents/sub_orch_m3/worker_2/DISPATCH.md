## 2026-08-23T13:10:15Z

You are Worker 2 (Replacement Worker) for Milestone 3 (Automated Growth Engine, Lead Generation & Telemetry).
Your Working Directory: c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m3\worker_2
Original Request Path: c:\Users\plumb\Desktop\claude-project\.agents\ORIGINAL_REQUEST.md
PROJECT.md Path: c:\Users\plumb\Desktop\claude-project\PROJECT.md
SCOPE.md Path: c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m3\SCOPE.md
Explorer 1 Report: c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m3\explorer_1\report.md
Explorer 2 Report: c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m3\explorer_2\report.md
Explorer 3 Report: c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m3\explorer_3\report.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Zero-Emoji Policy: STRICTLY ENFORCED. Zero Unicode emojis in any code, docstring, comment, or test fixture.

Write Ownership:
- `server/marketing.py`
- `server/reviews_ugc.py`
- `server/pricing_monitor.py`
- `server/models.py` (for M3 Pydantic schemas)
- `server/main.py` (for `/admin/mrr-metrics` enhancements)
- `tests/test_growth_engines.py`
- `tests/test_ugc_reviews.py`
- `tests/test_reddit_scout.py`
- `tests/test_seo_marketing.py`
- `tests/test_price_monitor.py`

Tasks to Implement:
1. Fix Critical Indentation Defect in `server/marketing.py` (`scan_reddit_opportunities`):
   - Move `found_count += 1`, `body = ...`, `_send_email(...)`, and `logger.info(...)` inside the `if any(kw in text for kw in SCOUT_KEYWORDS):` block immediately after `db.commit()`.
2. Harden SEO Blog Generation in `server/marketing.py` (`generate_seo_post`):
   - In bleach sanitization, add `strip_comments=True` and `protocols=['http', 'https', 'mailto']`.
   - Ensure `meta_desc` is truncated to max 160 chars (`data["meta_desc"][:160]`).
   - Harden slug creation with regex character cleaning (`re.sub(r'[^a-z0-9\-]+', '', slug.lower().replace(' ', '-')).strip('-')`) and a collision resolution loop against `BlogPost.slug`.
   - Expand `KEYWORDS` with high-intent e-commerce syndication terms.
3. Enhance Admin MRR Telemetry in `server/main.py` (`/admin/mrr-metrics`):
   - Import `PLANS` from `billing.py` to calculate tier prices dynamically.
   - Add churn metrics: `canceled_subscribers`, `past_due_subscribers`, `churn_rate_pct`.
   - Add response schema `AdminMRRMetricsResponse` in `server/models.py`.
4. Review Sentiment & UGC Drips in `server/reviews_ugc.py`:
   - Ensure 3-step post-purchase drip templates, positive/neutral/negative sentiment classifier, and automated merchant draft resolution replies are clean and robust.
5. Expand Test Suites:
   - In `tests/test_reddit_scout.py`: add tests for non-matching posts in Reddit batches (verifying no UnboundLocalError) and API failure handling.
   - In `tests/test_ugc_reviews.py`: add test for 3-star neutral review sentiment and negative text overriding positive star rating.
   - In `tests/test_seo_marketing.py`: add test for bleach XSS payload stripping and offline deterministic fallback.
   - In `tests/test_growth_engines.py`: add test for multi-tier MRR calculation and churn tracking.
   - In `tests/test_price_monitor.py`: add tests for edge cases (zero/negative selling price, competitor undercutting).
6. Verification:
   - Run `python -m pytest tests/ -v` and ensure 100% tests pass.
   - Run `python -m flake8 server --count --select=E9,F63,F7,F82` and ensure 0 errors.
   - Run `python tests/test_no_emojis.py` and ensure 0 emojis.
7. Write `c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m3\worker_2\handoff.md` with:
   - Observation (what was changed)
   - Logic Chain (why each change was made)
   - Caveats (any edge cases or assumptions)
   - Conclusion (summary of results)
   - Verification Commands and Outputs
8. Send completion message back to parent.
