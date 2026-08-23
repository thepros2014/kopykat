import pytest
from unittest.mock import patch, AsyncMock
from server.marketing import generate_seo_post
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
