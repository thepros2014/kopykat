# BRIEFING — 2026-08-23T10:24:00Z

## Mission
Implement Milestone 1: Multi-Modal Campaign & Platform Schemas across models, ai_engine, campaigns, main, and tests.

## 🔒 My Identity
- Archetype: worker
- Roles: implementer, qa, specialist
- Working directory: c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m1\worker_1
- Original parent: 53bd5b03-07b1-4711-a7b4-307d924c19c5
- Milestone: Milestone 1 (Multi-Modal Campaign & Platform Schemas)

## 🔒 Key Constraints
- Zero-Emoji Policy: STRICTLY ENFORCED across all code, docstrings, prompts, templates, and fallbacks.
- Mandatory Integrity Mandate: DO NOT cheat, fake test results, or create dummy implementations.
- Minimal change principle.
- Full verification with pytest, flake8, and test_no_emojis.py.

## Current Parent
- Conversation ID: 53bd5b03-07b1-4711-a7b4-307d924c19c5
- Updated: 2026-08-23T10:24:00Z

## Task Summary
- **What to build**:
  1. `server/models.py`: update `MarketplaceOptimizeRequest.platform` pattern, add `short_hooks`, `hashtags`, `sub_title`, `item_specifics` to `MarketplaceOptimizeResponse`.
  2. `server/ai_engine.py`: update prompts and offline deterministic fallbacks for amazon, shopify, etsy, tiktok/tiktok_shop, ebay with exact constraints.
  3. `server/campaigns.py`: add `_generate_fallback_vision_campaign`, enhance `_extract_clean_json` with regex fallback.
  4. `server/main.py`: update `/api/optimizer/marketplace-listing` response fields and `/api/campaign/generate-vision` dual-bucket usage.
  5. `tests/test_marketplace_schemas.py`: comprehensive tests covering all 5 platforms, constraints, validation, vision generation reservation/refund, and zero emojis.
- **Success criteria**: All tests pass, flake8 passes with 0 errors, no emojis, full schema compliance.
- **Interface contracts**: SCOPE.md, spec_report.md
- **Code layout**: server/ (backend), tests/ (unit tests)

## Key Decisions Made
- [TBD]

## Artifact Index
- DISPATCH.md — Initial instructions
- progress.md — Heartbeat and step tracking
- handoff.md — Final handoff report

## Change Tracker
- **Files modified**: None yet
- **Build status**: Pending
- **Pending issues**: None

## Quality Status
- **Build/test result**: Pending
- **Lint status**: Pending
- **Tests added/modified**: Pending

## Loaded Skills
- None
