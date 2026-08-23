# KopyKat — Autonomous SEO Blog Engine & Indexing System

The SEO Blog Engine generates and publishes search-optimized long-form articles targeting high-intent buyer keywords without manual intervention.

---

## 1. Publication Schedule & Cadence

- **Trigger:** Mon, Wed, Fri @ 09:00 UTC via APScheduler background daemon.
- **Manual Trigger:** `GET /admin/trigger-seo` (Requires `X-Admin-Secret` header).
- **Target Table:** `blog_posts` in PostgreSQL / SQLite.

---

## 2. Content Generation Pipeline

1. **Keyword Selection:** Selects from curated high-intent e-commerce search keywords.
2. **AI Article Drafting:** Prompts Google Gemini (`gemini-flash-latest`) to generate structured JSON containing title, URL-friendly slug, meta description, and HTML content (H2, H3, paragraphs, lists).
3. **HTML Sanitization:** Cleans all generated HTML via `bleach` allowing safe formatting tags while stripping unsafe scripts.
4. **Dynamic Sitemap Publishing:** The article slug is immediately discoverable via `GET /sitemap.xml`.
5. **Search Engine Ping:** Pings Google and Bing search crawlers to initiate fast indexing.
