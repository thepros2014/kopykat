# KopyKat launch and operator playbook

This playbook is for responsible pre-launch validation and early customer
discovery. It assumes the product has no established customer base or
validated conversion history. Replace every placeholder with verified project
information before publishing it.

## Before inviting users

1. Configure a staging deployment with managed PostgreSQL, separate secrets,
   test-mode Stripe keys, and a non-production AI account.
2. Run the backend and frontend verification commands in TEST_READY.md.
3. Test registration, login, password reset, API-key creation, quota
   reservation/refund, Stripe webhook replay, connector isolation, inventory
   replay handling, and generated-content rendering.
4. Confirm logs do not contain secrets, customer content, authorization
   headers, or full request bodies.
5. Add a support address, privacy notice, terms of use, data-retention
   policy, and a documented process for deleting test accounts.
6. Document which integrations are enabled and which remain experimental.

## First-user discovery

Start with a small, explicit cohort rather than broad automated outreach.

- Interview store owners, agencies, or operators who already manage multiple
  product listings.
- Ask for the workflow, current tools, time cost, and failure modes before
  presenting KopyKat.
- Offer a limited trial or guided setup only after obtaining clear consent.
- Record product feedback separately from financial or usage metrics.
- Do not describe a feature as live until it has been tested with the
  relevant provider account.

## Community outreach

When participating in forums or social communities:

- Follow each community's rules and disclose the relationship to KopyKat.
- Answer the question first; include a product reference only when relevant.
- Do not mass-post, scrape private areas, impersonate customers, or use
  automated replies without review.
- Respect deletion requests, rate limits, and platform API terms.
- Keep a record of approved messaging and remove claims that cannot be
  supported by product evidence.

## Weekly operating review

Review the following evidence from the instance and support channel:

- Activation: registrations that completed the first intended workflow.
- Reliability: error rates, provider failures, latency samples, and job runs.
- Safety: blocked requests, failed authentication, webhook replays, and
  connector errors.
- Product value: repeated user problems and requests, not vanity metrics.
- Cost: AI, hosting, email, payment, and marketplace-provider usage.

Use only persisted, time-bounded data. A zero or missing value is preferable to
an estimate presented as a fact.

## Go/no-go criteria

Pause public expansion if any of the following is true:

- Production secrets, database backups, or provider webhooks are unverified.
- A user can access another tenant's record.
- A failed AI or payment operation can consume credits or create a duplicate
  entitlement.
- A connector can reach private network addresses or follow uncontrolled
  redirects.
- Customer-facing output contains unsupported claims or unsafe HTML.
- Support, incident response, or data-deletion ownership is undefined.

## Message template

Use a factual invitation such as:

> We are testing KopyKat, a tool for generating and organizing e-commerce
> catalog and marketing content. We are looking for operators who can review a
> specific workflow and tell us where it fails. There is no claim of existing
> customer results; the goal is product feedback. If you are interested, we
> can provide a controlled test account and a short feedback session.
