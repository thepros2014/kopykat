# Handoff Report: Explorer 2 (Milestone 1)

**Milestone**: Milestone 1 (Multi-Modal Campaign & Platform Schemas)  
**Agent**: Explorer 2 (`sub_orch_m1/explorer_2`)  
**Parent**: `53bd5b03-07b1-4711-a7b4-307d924c19c5`  
**Date**: 2026-08-23  

---

## 1. Observation

1. **Vision Engine (`server/campaigns.py:152–250`)**:
   - `generate_omni_campaign_from_image` accepts `(image_bytes: bytes, mime_type: str, keyword: str = "", extra_context: str = "") -> dict`.
   - Generates prompts requiring strict JSON keys: `detected_product_name`, `detected_description`, `blog_post` (`title`, `content`), `email_drip` (3 items with `subject`, `body`), and `social_posts` (3 strings).
   - Supports Gemini Vision (`gemini-1.5-flash`) and OpenAI Vision (`gpt-4o-mini`). Falls back from Gemini to OpenAI when Gemini fails and `OPENAI_API_KEY` is present.
   - If neither key is configured or both fail, it raises `ValueError("No AI API key configured...")` / `ValueError("Vision campaign generation failed: ...")`. It has **no deterministic offline fallback**.
   - `_extract_clean_json` (lines 141–149) strips markdown code wrappers via `.startswith("```json")` but lacks regex extraction (`re.search(r'\{.*\}', ...)`) for resilience against extraneous LLM commentary.

2. **Endpoint Invariants (`server/main.py:602–657`)**:
   - In `POST /api/campaign/generate-vision` (lines 619–624):
     ```python
     updated = db.execute(
         text("UPDATE users SET generations = generations - 1 WHERE id = :uid AND generations >= 1"),
         {"uid": user.id}
     ).rowcount
     ```
   - In the exception handlers (lines 646–656):
     ```python
     except ValueError as e:
         db.rollback()
         db.execute(text("UPDATE users SET generations = generations + 1 WHERE id = :uid"), {"uid": user.id})
         db.commit()
         raise HTTPException(status_code=400, detail=str(e))
     except Exception as e:
         db.rollback()
         db.execute(text("UPDATE users SET generations = generations + 1 WHERE id = :uid"), {"uid": user.id})
         db.commit()
         raise HTTPException(status_code=500, detail="Vision generation failed due to an internal error. Your balance was refunded.")
     ```
   - In contrast, `POST /api/campaign/generate` (lines 586–600) correctly uses `monthly_used, purchased_used = reserve_user_generations(user.id, 1, db)` and `refund_user_generations(user.id, monthly_used, purchased_used, db)`.

3. **Payload Handling & Schemas (`server/models.py:157–162`)**:
   - `CampaignVisionGenerateRequest` defines `keyword`, `extra_context`, `image_base64: str = Field(min_length=10)`, and `mime_type: Optional[str] = "image/jpeg"`.
   - In `server/main.py:627–630`, data URLs are handled via `raw_b64.split(",", 1)[1]` prior to `base64.b64decode`. There is no remote `image_url` ingestion support in the model.

4. **Zero-Emoji Compliance (`tests/test_no_emojis.py`)**:
   - `test_zero_emojis_in_codebase` passed with 0 violations across `server/` and `frontend/`.
   - Full test suite (`python -m pytest tests/ -v`) passed 65/65 tests.
   - `flake8 server --count --select=E9,F63,F7,F82` returned 0 errors.

---

## 2. Logic Chain

1. **Dual-Bucket Quota Model Invariant**:
   - *Observation*: PROJECT.md §F17 specifies a dual-bucket balance model managed by centralized `reserve_user_generations` and `refund_user_generations`.
   - *Observation*: `api_campaign_generate_vision` directly modifies `users.generations` via raw SQL without altering `monthly_generations` or `purchased_generations`.
   - *Inference*: Any call to `/api/campaign/generate-vision` desynchronizes the user's bucket ledger where `monthly_generations + purchased_generations != generations`.

2. **Critical Infinite Credit Generation Exploit**:
   - *Observation*: In `api_campaign_generate_vision`, the initial SQL `UPDATE users SET generations = generations - 1` is uncommitted before the AI generation try-block.
   - *Observation*: On failure (e.g. invalid base64 or AI error), `db.rollback()` executes first, canceling the uncommitted decrement and returning `generations` to its starting value.
   - *Observation*: Next, `UPDATE users SET generations = generations + 1` executes and commits.
   - *Inference*: On every failure, the user's generation balance increases by 1 credit, creating a high-severity credit inflation exploit.

3. **Offline Fallback Resilience**:
   - *Observation*: `server/ai_engine.py` provides deterministic offline fallbacks for all marketplace platforms, ensuring reliability without external API keys.
   - *Observation*: `server/campaigns.py` raises `ValueError` when API keys are absent or API calls fail.
   - *Inference*: Introducing a deterministic fallback in `generate_omni_campaign_from_image` will ensure zero downtime and reliable offline test execution.

---

## 3. Caveats

1. **Async Event-Loop Concurrency**: `generate_omni_campaign_from_image` performs synchronous network I/O to Gemini/OpenAI inside an `async def` FastAPI route. While functional, high concurrent traffic would benefit from asynchronous HTTP or `asyncio.to_thread`.
2. **Remote Image URL Fetching**: Currently, only base64 image data is supported in `CampaignVisionGenerateRequest`. If future requirements introduce `image_url`, it must strictly use `SafeAsyncHTTPClient` with SSRF and DNS-rebinding protection.

---

## 4. Conclusion

1. **Vision Pipeline**: Multi-modal prompt engineering and dual-provider support (Gemini + OpenAI) are well structured, but require deterministic offline fallback handling and resilient JSON extraction.
2. **Quota Invariant**: `POST /api/campaign/generate-vision` in `server/main.py` has a critical financial flaw and must be updated to use `reserve_user_generations` and `refund_user_generations`.
3. **Zero-Emoji**: Codebase is 100% compliant with zero-emoji standards.

---

## 5. Verification Method

To independently verify these findings:

1. **Inspect Code Locations**:
   - Check `server/main.py:619–656` for the raw SQL update and rollback behavior vs `server/main.py:586–600`.
   - Check `server/campaigns.py:152–250` for missing offline fallback handling.
   - Check `server/models.py:157–162` for `CampaignVisionGenerateRequest` definition.

2. **Execute Test Suite**:
   ```pwsh
   python -m pytest tests/ -v
   python -m flake8 server --count --select=E9,F63,F7,F82
   python -m pytest tests/test_no_emojis.py
   ```
