# SEO content engine

The SEO engine creates draft-ready blog posts, stores sanitized HTML, and
exposes sitemap and robots metadata. Publication and search indexing are not
guaranteed; review generated claims and configure the public URL first.

## Schedule

- Automatic generation: Monday, Wednesday, and Friday at 14:00 UTC.
- Manual generation: POST /admin/trigger-seo with the x-admin-secret header.
- Analytics: GET /api/seo/analytics with an authenticated bearer credential.
- Index ping: POST /api/seo/ping-index with an authenticated bearer credential.

The manual admin route is intentionally excluded from the public OpenAPI
schema. Keep ADMIN_SECRET in a secret manager.

## Generation flow

1. Select a configured keyword or the requested keyword.
2. Use the selected AI provider, preferring AI_PROVIDER and falling back to
   the other configured provider when supported.
3. Parse the structured title, slug, meta description, and HTML content.
4. Sanitize HTML with the configured allowlist.
5. Resolve slug collisions before persistence.
6. Expose published records through the blog, sitemap, and analytics routes.

If no provider is available or a provider fails, the service creates a
deterministic limited fallback article. A fallback is not a substitute for
editorial review.

## Supported provider configuration

- OpenAI: OPENAI_API_KEY and OPENAI_MODEL.
- Gemini: GEMINI_API_KEY and GEMINI_MODEL.
- Preference: AI_PROVIDER=openai or AI_PROVIDER=gemini.

The provider key remains server-side. Do not put it in browser code or a
generated article.

## Content controls

Generated HTML is restricted to safe semantic elements and safe URL
protocols. Review links, product claims, disclosures, and brand references
before publishing. Search-engine pings request crawling; they do not ensure
indexing or ranking.
