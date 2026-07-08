import pytest
from app.api.v1.endpoints.chat import _markdown_to_reportlab_html, _generate_file_native
from unittest.mock import patch, MagicMock

def test_markdown_to_reportlab_html_escaping():
    # Test ampersand and angle brackets escaping
    res1 = _markdown_to_reportlab_html("Colonialism & imperialism <legacy>")
    assert res1 == "Colonialism &amp; imperialism &lt;legacy&gt;"

def test_markdown_to_reportlab_html_formatting():
    # Test bold, italic, code, and links formatting
    text = "This is **bold**, this is *italic*, code is `print('hello')`, and [Google](https://google.com) link."
    expected = (
        "This is <b>bold</b>, this is <i>italic</i>, "
        "code is <font name=\"Courier\">print('hello')</font>, "
        "and <a href=\"https://google.com\" color=\"blue\"><u>Google</u></a> link."
    )
    assert _markdown_to_reportlab_html(text) == expected

def test_markdown_to_reportlab_html_mismatched_html_safe():
    # Mismatched HTML tags should get safely escaped to avoid ReportLab parsing exceptions
    text = "Mismatched <b>bold tag"
    expected = "Mismatched &lt;b&gt;bold tag"
    assert _markdown_to_reportlab_html(text) == expected

@pytest.mark.asyncio
async def test_generate_file_native_pdf_fallback():
    # Verify that if doc.build fails, it gracefully falls back and succeeds
    content = "This content has a mismatched tag <b> inside text."
    
    # We will mock the upload helper so we only test generation logic
    with patch("app.api.v1.endpoints.chat._upload_generated_file") as mock_upload:
        mock_upload.return_value = "mock_r2_url"
        
        url = await _generate_file_native(
            content=content,
            filename="test_fallback",
            fmt="pdf",
            conversation_id="test_convo",
            user_id="test_user"
        )
        
        assert url == "mock_r2_url"
        mock_upload.assert_called_once()
        # Verify it was called with PDF mimetype
        args, kwargs = mock_upload.call_args
        assert kwargs["mime_type"] == "application/pdf"
        assert len(kwargs["file_bytes"]) > 0
