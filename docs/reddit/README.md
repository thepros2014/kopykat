# Opportunity scout

The opportunity scout is an internal lead-research workflow. It reads the
configured public Reddit JSON feeds, matches a small set of e-commerce
copywriting terms, stores a relevance score, and drafts a possible reply for
human review. It does not publish replies.

## Schedule and controls

- Schedule: every four hours at minute 15 UTC.
- Sources: the configured public Reddit subreddit feeds.
- Storage: opportunity_logs.
- Review route: GET /api/leads with an authenticated bearer credential.
- Notification: OWNER_EMAIL is used only when an email service is configured.

Disable or remove the scheduler job if the deployment has not reviewed
Reddit's current API rules, rate limits, robots policy, and applicable
privacy requirements. Use a clear user agent and low request volume.

## Drafting providers

The scout can draft with:

- OpenAI, when AI_PROVIDER=openai and OPENAI_API_KEY is configured.
- Gemini, when AI_PROVIDER=gemini and GEMINI_API_KEY is configured.
- A deterministic fallback when no provider is available.

Provider keys remain server-side. Generated replies must be reviewed for
accuracy, disclosure, relevance, and community rules before any manual use.

## Prohibited automation boundary

This module is not a general-purpose scraper or auto-poster. Do not point it
at a new community without a terms review and explicit permission where
required. In particular, Moltbook's current terms prohibit automated devices,
scraping, and unauthorized advertising or commercial sales content. KopyKat
does not implement an automated Moltbook visitor or poster.

## Safe operating procedure

1. Confirm the source terms and API access before enabling the job.
2. Review the lead and source context in the dashboard.
3. Remove personal or sensitive information from any draft.
4. Edit the response to answer the question without making unsupported claims.
5. Disclose the relationship to KopyKat where the community requires it.
6. Publish manually only when the platform rules allow it.
