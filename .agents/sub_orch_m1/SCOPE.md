# Scope: Milestone 1 (Multi-Modal Campaign & Platform Schemas)

## Architecture
- Target files:
  - `server/models.py`: Pydantic request/response models (`MarketplaceOptimizeRequest`, `CampaignVisionGenerateRequest`, etc.).
  - `server/ai_engine.py`: Structured platform generators, character/byte constraints, fallback generators, compliance scoring.
  - `server/campaigns.py`: Multi-modal vision product analysis and omni-channel campaigns.
  - `tests/test_marketplace_schemas.py`: Unit tests for marketplace schemas.
  - `tests/test_addons_monetization.py`: Monetization/campaign tests.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F1 | Multi-Modal Vision Pipeline | Image-based product analysis and omni-channel campaign generation via Gemini/OpenAI with atomic balance reservation & failure refund | M1 | ORIGINAL_REQUEST §1 |
| F2 | Amazon Listing Schema | Structured output: Title <200 chars, 5 bullet points, backend keywords <249 bytes, compliance score, deterministic offline fallback | M1 | ORIGINAL_REQUEST §1 |
| F3 | Shopify Listing Schema | Structured output: Title <70 chars, meta description <155 chars, 4 bullets, DTC HTML description, compliance score, fallback | M1 | ORIGINAL_REQUEST §1 |
| F4 | Etsy Listing Schema | Structured output: Title <140 chars, 13 long-tail tags (<20 chars), 3-4 bullets, warm artisan description, compliance score, fallback | M1 | ORIGINAL_REQUEST §1 |
| F5 | TikTok Shop Listing Schema | Structured output: Title <100 chars (Viral hook + Product + Benefit), 3-5 punchy bullets, 3 video hooks/scripts, 5-8 trending hashtags, mobile description, compliance score, fallback | M1 | ORIGINAL_REQUEST §1 |
| F6 | eBay Listing Schema | Structured output: Title <80 chars, subtitle <55 chars, item specifics dict, 3-4 bullets, HTML listing template with policies, compliance score, fallback | M1 | ORIGINAL_REQUEST §1 |

## Interface Contracts
`server/ai_engine.py`: `optimize_marketplace_listing(product_name, platform, raw_details="", keywords="", target_audience="", brand_persona=None) -> dict`
Platform Regex: `^(amazon|shopify|etsy|tiktok|tiktok_shop|ebay)$`
Deterministic offline fallbacks for all 5 platforms must return compliant structures.
Zero-emoji policy in all outputs and source code.
