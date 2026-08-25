# Security and Error Scan

Scan date: 2026-08-24. Scope: the active outer checkout at the repository root,
including the FastAPI server, browser clients, React client, tests, billing
flows, and tracked configuration templates.

## Remediated in this pass

- Browser sessions no longer persist JWTs in Web Storage. Login and registration
  issue an `HttpOnly`, `SameSite=Lax` session cookie; bearer tokens remain
  supported for API clients.
- The landing-page login now sends the JSON shape expected by the API.
- Dropship partner contacts remain deployment-only. Invitation tokens are stored
  as hashes, public projections contain no contact data or private pricing, and
  Stripe server-side configuration selects the checkout price.
- Featured placement is limited to five slots. Ranked directory placement has
  eight annual slots. Slot reservations use a database composite key so
  concurrent checkout attempts cannot silently purchase the same position.
- Stripe partner events remain signature-verified and event-ID idempotent.
  Canceled placements are removed from the public projection and their slot is
  released.
- Public partner and featured-partner rendering uses bounded HTTPS URL checks
  and DOM text APIs. Dashboard rich text is passed through an allowlist
  sanitizer before insertion.
- Unsupported public plan and support claims were removed or aligned with the
  configured billing entitlements.
- Stale runtime duplicates and exports with no repository references were
  removed: `worker.py`, `products.csv`, `schema.json`, and `updates snap 2.txt`.

## Checks run

| Check | Result |
| --- | --- |
| `python -m pytest -q` | 435 passed, 9 warnings |
| Focused auth/partner/security tests | Passed |
| `python -m compileall -q server tests` | Passed |
| `git diff --check` | Passed; only Git line-ending warnings |
| Bandit, server scan | No medium/high issues; 16 low-confidence informational findings |
| `pip-audit -r requirements.txt` | No known vulnerabilities |
| React `npm run build` | Passed |
| React `npm audit --audit-level=high` | 0 vulnerabilities |
| targeted undefined-name/syntax Flake8 checks | Clean after remediation; broad style check is legacy-noisy |

## Findings that still need operational attention

1. The local `.env` contained a live Stripe secret. It was not tracked by Git
   and was moved to the external local archive
   `C:\Users\plumb\Desktop\claude-project-local-archive-2026-08-24`. Rotate that
   Stripe secret immediately if it has ever been shared, backed up, or exposed
   outside the intended deployment secret store.
2. The installed Python environment has unrelated package conflicts reported by
   `pip check` (`opencv-python-headless`/NumPy, TensorBoard/protobuf, and
   torchvision/Torch). They are not direct dependencies in `requirements.txt`;
   rebuild the environment from the pinned requirements for a clean deployment
   check.
3. The legacy HTML clients still contain inline scripts and the admin page uses
   the Tailwind browser CDN. CSP therefore retains `unsafe-inline` and explicitly
   allows that CDN. Replace those pages with nonce-based scripts and a pinned,
   locally served CSS build before treating the app as hardened against supply
   chain or injected-script risk.
4. The broad Flake8 run reports legacy formatting findings across the preexisting
   codebase. This pass removed the actionable unused exception bindings and keeps
   the targeted syntax/name checks clean; formatting cleanup should be a separate
   mechanical change to avoid mixing it with billing behavior.

This report is an evidence record, not a production certification. Production
certification still requires a clean deployment environment, secret rotation
where applicable, configured Stripe Price IDs/webhook secrets, and a successful
CI/deployment run.
