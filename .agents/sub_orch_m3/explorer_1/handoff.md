# Handoff Report: Milestone 3 SEO Blog Engine & Reddit Opportunity Scout

**Explorer**: Explorer 1  
**Milestone**: Milestone 3 (Automated Growth Engine, Lead Generation & Telemetry)  
**Type**: Hard Handoff  
**Zero-Emoji Status**: 100% Compliant

---

## 1. Observation

1. **Reddit Scout Indentation Bug in `server/marketing.py:214-253`**:
   Lines 214-253 of `server/marketing.py`:
   ```python
   214:                     if any(kw in text for kw in SCOUT_KEYWORDS):
   215:                         if db.query(OpportunityLog).filter_by(post_id=post_id).first():
   216:                             continue
   ...
   245:                         db.add(log)
   246:                         db.commit()
   247:                     found_count += 1
   248: 
   249:                     body = f"Found a lead on r/{sub}!<br><br><b>{title}</b><br><a href='{url}'>{url}</a><br><br><b>Draft Reply to copy/paste:</b><br>{draft}"
   250:                     _send_email(f"New Lead: {title[:30]}...", body, os.environ.get("OWNER_EMAIL", ""))
   251:                     logger.info("Found opportunity on r/%s: %s", sub, title[:30])
   ```
   Lines 247-251 are indented with 20 spaces (outside the `if any(kw in text for kw in SCOUT_KEYWORDS):` block), which executes for all posts in a subreddit feed regardless of whether they matched keywords.

2. **Bleach Sanitization Configuration**:
   In `server/marketing.py:93-100`:
   ```python
   allowed_tags = ["h2", "h3", "p", "ul", "ol", "li", "b", "strong", "em", "a"]
   allowed_attrs = {"a": ["href", "title", "rel", "target"]}
   sanitized_content = bleach.clean(
       data["content"], 
       tags=allowed_tags, 
       attributes=allowed_attrs, 
       strip=True
   )
   ```
   In `server/main.py:66-67`:
   ```python
   _ALLOWED_TAGS=["p","h2","h3","h4","ul","ol","li","strong","em","b","i","a","br","blockquote"]
   _ALLOWED_ATTRS={"a":["href","title","rel"]}
   def sanitize_html(raw:str)->str: return bleach.clean(raw,tags=_ALLOWED_TAGS,attributes=_ALLOWED_ATTRS,strip=True,strip_comments=True)
   ```
   `server/marketing.py` lacks `strip_comments=True` and explicit protocol validation (`protocols=["http", "https", "mailto"]`).

3. **SEO Post Slug Generation**:
   In `server/marketing.py:51-53`:
   ```python
   slug_base = keyword.lower().replace(" ", "-")
   if db.query(BlogPost).filter(BlogPost.slug == slug_base).first():
       slug_base = f"{slug_base}-{random.randint(100, 999)}"
   ```
   Special characters or punctuation in `keyword` (such as `?`, `/`, `,`) are not sanitized by `replace(" ", "-")`.

4. **Intent Scoring Logic in `server/marketing.py:229-234`**:
   ```python
   intent_score = 75
   if any(high_kw in text for high_kw in ["need a copywriter", "hire", "budget", "pay", "sucks at writing", "struggling"]):
       intent_score += 15
   if "ecommerce" in sub or "shopify" in text or "amazon" in text:
       intent_score += 8
   intent_score = min(intent_score, 99)
   ```
   Minimum score is 75, bonuses raise score up to 98 (75+15+8), and `min(intent_score, 99)` caps at 99.

5. **Existing Test Suite Execution**:
   - Command: `python -m pytest tests/ -v`
   - Result: 65 passed, 7 warnings in 22.47s.
   - Command: `python -m flake8 server --count --select=E9,F63,F7,F82`
   - Result: 0 errors.
   - Command: `python -m pytest tests/test_no_emojis.py -v`
   - Result: 1 passed, 0 emojis detected across `server/` and `frontend/`.

---

## 2. Logic Chain

1. From Observation 1, if the Reddit feed contains a post that does not match `SCOUT_KEYWORDS`, execution proceeds past the `if` block to line 247 where `found_count` is incremented. At line 249, `draft` is accessed in the f-string. If no matching post was previously encountered in the function execution, `draft` has never been assigned, triggering an `UnboundLocalError`. The exception handler catches this and returns `0`, terminating the scan of that subreddit prematurely.
2. From Observation 2, while bleach is used, missing `strip_comments=True` allows HTML comments to persist in database storage, and omitting `protocols` leaves default URL handling instead of an explicit whitelist.
3. From Observation 3, raw keywords converted to slugs using only string replacement risk containing URL-unsafe characters (e.g. `how-to-write-product-descriptions-with-ai?`). A regex slugifier ensures pure `[a-z0-9\-]` characters.
4. From Observation 4, the scoring algorithm guarantees the 75-99 range requirement for discovered leads.
5. From Observation 5, all current baseline tests pass, confirming the system is structurally healthy and ready for targeted fixes.

---

## 3. Caveats

- Reddit live API queries require network access and may be rate-limited by Reddit in production if invoked without an OAuth token; `httpx.AsyncClient` with a realistic `User-Agent` and timeout of 5.0s is used, and unit tests mock `httpx.AsyncClient.get`.
- Gemini API key is optional for testing environments; deterministic fallbacks exist for both SEO post generation and Reddit draft replies.
- Telemetry/MRR metrics and UGC review sentiment logic were reviewed for integration context; detailed exploration for those components is covered by peer subagents.

---

## 4. Conclusion

The SEO Blog Generation Engine and Reddit Opportunity Scout are structurally well-designed and feature-complete, but require three critical fixes and enhancements during implementation:
1. Fix the indentation bug in `server/marketing.py:scan_reddit_opportunities` to ensure `found_count`, email alerts, and logging only run for matched, freshly logged leads.
2. Harden `server/marketing.py:generate_seo_post` with regex slug sanitization, `meta_desc` length bounds (<160 chars), and explicit bleach sanitization parameters (`strip_comments=True`, `protocols=['http', 'https', 'mailto']`).
3. Maintain zero emojis across all code, tests, and comments.

---

## 5. Verification Method

To independently verify these findings:
1. Inspect `server/marketing.py` lines 205-255 to verify the indentation of lines 247-251.
2. Run the test suite:
   ```bash
   python -m pytest tests/test_seo_marketing.py tests/test_reddit_scout.py tests/test_growth_engines.py -v
   ```
3. Run the zero-emoji test:
   ```bash
   python -m pytest tests/test_no_emojis.py -v
   ```
4. Run flake8 syntax and undefined variable checks:
   ```bash
   python -m flake8 server --count --select=E9,F63,F7,F82
   ```
5. Invalidation Condition: If `scan_reddit_opportunities` is called with a mocked Reddit response where the first child post has `title="Unrelated post"` and `selftext="Nothing relevant"`, the function should not raise `UnboundLocalError` nor should it send an email for the non-matching post.
