# Email drip scheduler

The email drip job prepares and sends configured onboarding or upgrade
messages to eligible free-plan users. It is a product workflow, not a
guaranteed conversion system. Configure delivery, consent, unsubscribe
handling, and support ownership before enabling it.

## Schedule

- Runs daily at 10:00 UTC.
- Selects users whose plan is free.
- Uses account age to select the day-2, day-4, or day-7 step.
- Records each sent step in drip_logs.

## Idempotency

Before sending, the job checks for an existing record with the same user ID
and step. It creates the delivery record after the mail call succeeds. Review
delivery-provider behavior and add an outbox or provider idempotency key if
the deployment requires stronger delivery guarantees.

## Content and configuration

Message templates are stored in server/marketing.py. They should:

- Identify the sender and include a support address.
- Avoid unverified savings, performance, or customer-result claims.
- Include an unsubscribe or preference path appropriate to the mail provider.
- Use a current application URL from configuration rather than a hard-coded
  deployment URL.

Email delivery requires the configured provider settings, OWNER_EMAIL or
SUPPORT_EMAIL as appropriate, and a tested non-production account.

## Analytics

Authenticated GET /api/drip/analytics reports persisted counts for free users,
sent steps, paying users, and the calculated instance conversion rate. The
values describe the current database; they are not a forecast or a public
marketing claim.
