import pytest
import json
from unittest.mock import patch, AsyncMock
from server.marketing import generate_seo_post, _clean_slug, _resolve_unique_slug
from server.database import BlogPost

@pytest.mark.asyncio
async def test_generate_seo_post(db_session):
    mock_ai_json = '{"title": "How to Supercharge Ecommerce Conversions", "slug": "supercharge-ecommerce-conversions", "meta_desc": "Discover the top strategies for ecommerce growth.", "content": "<h2>Higher Conversions</h2><p>Here are proven techniques.</p>"}'
    
    mock_resp = AsyncMock()
    mock_resp.text = mock_ai_json

    with patch("google.generativeai.GenerativeModel.generate_content_async", return_value=mock_resp):
        post = await generate_seo_post(db=db_session)
        assert post is not None
        assert post.title == "How to Supercharge Ecommerce Conversions"
        assert post.slug == "supercharge-ecommerce-conversions"
        assert post.published is True

        # Verify persistent storage in database
        db_post = db_session.query(BlogPost).filter(BlogPost.id == post.id).first()
        assert db_post is not None
        assert db_post.word_count > 0

def test_sitemap_and_robots_endpoints(client, db_session):
    # Test robots.txt
    robots_res = client.get("/robots.txt")
    assert robots_res.status_code == 200
    assert "Sitemap:" in robots_res.text
    assert "User-agent: *" in robots_res.text

    # Test sitemap.xml
    sitemap_res = client.get("/sitemap.xml")
    assert sitemap_res.status_code == 200
    assert "<?xml" in sitemap_res.text
    assert "<urlset" in sitemap_res.text
    assert "/blog" in sitemap_res.text


@pytest.mark.asyncio
async def test_generate_seo_post_bleach_xss_sanitization(db_session):
    """Verifies that bleach strips script tags, iframes, comments, and javascript: links."""
    mock_ai_json = '{"title": "SEO Security Guide", "slug": "seo-security-guide", "meta_desc": "Secure blog generation.", "content": "<h2>Clean Header</h2><!-- malicious comment --><script>alert(\'xss\')</script><p>Safe text with <a href=\\"javascript:alert(\'pwn\')\\">malicious link</a> and <a href=\\"https://kopykat.onrender.com\\">valid link</a>.<iframe src=\\"http://evil.com\\"></iframe></p>"}'
    
    mock_resp = AsyncMock()
    mock_resp.text = mock_ai_json

    with patch("google.generativeai.GenerativeModel.generate_content_async", return_value=mock_resp):
        post = await generate_seo_post(db=db_session)
        assert post is not None
        assert "<script>" not in post.content
        assert "</script>" not in post.content
        assert "<iframe" not in post.content
        assert "javascript:" not in post.content
        assert "malicious comment" not in post.content
        assert "<h2>Clean Header</h2>" in post.content
        assert "https://kopykat.onrender.com" in post.content


@pytest.mark.asyncio
async def test_generate_seo_post_offline_fallback(db_session):
    """Verifies deterministic fallback generation when GEMINI_API_KEY is not configured."""
    with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
        post = await generate_seo_post(db=db_session)
        assert post is not None
        assert post.published is True
        assert len(post.slug) > 0
        assert len(post.meta_desc) <= 160
        assert post.word_count > 0
        
        saved = db_session.query(BlogPost).filter(BlogPost.id == post.id).first()
        assert saved is not None


@pytest.mark.asyncio
async def test_generate_seo_post_adversarial_xss_vectors(db_session):
    """Stress tests bleach against nested scripts, event handlers, protocols, and styling."""
    adversarial_html = """
    <h2>Heading 2</h2>
    <!-- normal comment -->
    <!--[if IE]><script>alert('ie')</script><![endif]-->
    <script><script>alert('nested')</script></script>
    <p onmouseover="alert('xss')" onload="alert('pwn')">Paragraph with <b onclick="alert(1)">bold</b></p>
    <a href="JAVASCRIPT:alert('proto')">Upper JS</a>
    <a href="data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==">Data URI</a>
    <a href="vbscript:msgbox('vb')">VBScript URI</a>
    <a href="https://valid.com" target="_blank" rel="noopener" style="color:red" onclick="evil()">Safe Link</a>
    <svg><script>alert('svg')</script></svg>
    <math><mtext><table><mglyph><style><!--</style><img src=x onerror=alert('math')></math>
    <style>body { background: red; }</style>
    <object data="evil.swf"></object>
    <embed src="evil.swf">
    """
    mock_ai_json = f'{{"title": "Adversarial XSS Test", "slug": "adversarial-xss-test", "meta_desc": "Testing security.", "content": {json.dumps(adversarial_html)}}}'
    mock_resp = AsyncMock()
    mock_resp.text = mock_ai_json

    with patch("google.generativeai.GenerativeModel.generate_content_async", return_value=mock_resp):
        post = await generate_seo_post(db=db_session)
        assert post is not None
        content = post.content.lower()
        assert "<script" not in content
        assert "onload" not in content
        assert "onmouseover" not in content
        assert "onclick" not in content
        assert "onerror" not in content
        assert "javascript:" not in content
        assert "data:" not in content
        assert "vbscript:" not in content
        assert "<svg" not in content
        assert "<math" not in content
        assert "<style" not in content
        assert "<object" not in content
        assert "<embed" not in content
        assert "<!--" not in content
        assert "<h2>heading 2</h2>" in content
        assert '<a href="https://valid.com"' in post.content
        assert 'target="_blank"' in post.content
        assert 'rel="noopener"' in post.content


@pytest.mark.asyncio
async def test_seo_slug_collision_and_cleaning_stress(db_session):
    """Stress tests slug collision resolution under repeated generations and extreme raw slugs."""
    assert _clean_slug("") == "kopykat-guide"
    assert _clean_slug("   ") == "kopykat-guide"
    assert _clean_slug("!@#$%^&*()_+{}[]") == "kopykat-guide"
    assert _clean_slug("---leading-and-trailing---") == "leading-and-trailing"
    assert _clean_slug("How  To   Write   Product   Descriptions") == "how-to-write-product-descriptions"
    assert _clean_slug("电商增长指南") == "kopykat-guide"

    base_slug = "stress-test-slug"
    created_slugs = []
    for i in range(25):
        unique_slug = _resolve_unique_slug(db_session, base_slug)
        post = BlogPost(
            id=f"post_collision_{i}",
            title=f"Collision Title {i}",
            slug=unique_slug,
            keyword="collision test",
            meta_desc="Testing collision resolution",
            content="<p>Body</p>",
            word_count=5,
            published=True
        )
        db_session.add(post)
        db_session.commit()
        created_slugs.append(unique_slug)

    assert len(set(created_slugs)) == 25
    assert created_slugs[0] == "stress-test-slug"
    assert created_slugs[1] == "stress-test-slug-1"
    assert created_slugs[24] == "stress-test-slug-24"


@pytest.mark.asyncio
async def test_generate_seo_post_extreme_inputs(db_session):
    """Verifies handling of markdown wrappers, oversized meta description, and corrupted JSON."""
    wrapped_json = '```json\n{"title": "Wrapped Title", "slug": "wrapped-slug", "meta_desc": "Desc", "content": "<p>Wrapped</p>"}\n```'
    mock_resp = AsyncMock()
    mock_resp.text = wrapped_json

    with patch("google.generativeai.GenerativeModel.generate_content_async", return_value=mock_resp):
        post = await generate_seo_post(db=db_session)
        assert post is not None
        assert post.title == "Wrapped Title"
        assert post.slug == "wrapped-slug"

    huge_desc = "A" * 5000
    huge_json = f'{{"title": "Huge Desc Title", "slug": "huge-desc", "meta_desc": "{huge_desc}", "content": "<p>Content</p>"}}'
    mock_resp.text = huge_json

    with patch("google.generativeai.GenerativeModel.generate_content_async", return_value=mock_resp):
        post = await generate_seo_post(db=db_session)
        assert post is not None
        assert len(post.meta_desc) == 160

    mock_resp.text = "This is not JSON at all {{broken}}"
    with patch("google.generativeai.GenerativeModel.generate_content_async", return_value=mock_resp):
        post = await generate_seo_post(db=db_session)
        assert post is not None
        assert "The Complete Guide to" in post.title
