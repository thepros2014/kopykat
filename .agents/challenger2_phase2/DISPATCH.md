## 2026-08-23T18:47:29Z

You are Challenger 2 for Phase 2: Tier 5 Adversarial Coverage Hardening.

Your Working Directory: c:\Users\plumb\Desktop\claude-project\.agents\challenger2_phase2
Original Request Path: c:\Users\plumb\Desktop\claude-project\.agents\ORIGINAL_REQUEST.md
PROJECT.md Path: c:\Users\plumb\Desktop\claude-project\PROJECT.md
TEST_READY.md Path: c:\Users\plumb\Desktop\claude-project\TEST_READY.md
Project Root: c:\Users\plumb\Desktop\claude-project

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations and tests must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Mission:
Perform white-box adversarial analysis of the server codebase (`server/`) and existing test suites (`tests/`).
Design and author robust adversarial pytest test cases targeting:
1. Extreme Marketplace Inputs: Unicode edge characters, RTL text, massive prompt injections, XSS/HTML injection into title/bullets/tags, null bytes, exact boundary limits (200 chars Amazon title, 13 tags Etsy, 70 chars Shopify).
2. Malformed & Rapid Duplicate Webhooks: Corrupted payloads, missing signatures, concurrent duplicate webhook deliveries, negative quantity webhook stock adjustments.
3. Drift Reconciliation & Multi-Channel Fanout Race Conditions: Rapid inventory updates during background drift reconciliation, circular fanout webhook loops, connector connection failure handling.
4. Zero-Emoji Compliance Adversarial Attacks: Prompt injections attempting to force emoji generation in AI copy, fallback templates, blog generation, and review responses.

Deliverables:
- Author standalone, runnable pytest functions and write them to `c:\Users\plumb\Desktop\claude-project\.agents\challenger2_phase2\adversarial_tests.py`.
- Run your tests against the server codebase using `python -m pytest c:\Users\plumb\Desktop\claude-project\.agents\challenger2_phase2\adversarial_tests.py -v` (or in project root) to test the implementation.
- Document all findings, edge cases, test coverage, and fix recommendations in `c:\Users\plumb\Desktop\claude-project\.agents\challenger2_phase2\handoff.md`.
- Send a completion message to your parent.
