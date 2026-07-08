import pytest
from docx import Document
from unittest.mock import patch
from app.api.v1.endpoints.chat import _apply_inline_docx, _generate_file_native

def test_apply_inline_docx_formatting():
    # Create a document and a paragraph to test
    doc = Document()
    p = doc.add_paragraph()
    
    test_text = "Standard text, **bold text**, *italic text*, and **bold again**."
    _apply_inline_docx(p, test_text)
    
    # We expect runs:
    # 1. "Standard text, " (normal)
    # 2. "bold text" (bold)
    # 3. ", " (normal)
    # 4. "italic text" (italic)
    # 5. ", and " (normal)
    # 6. "bold again" (bold)
    # 7. "." (normal)
    
    runs = p.runs
    assert len(runs) >= 6
    
    # Verify standard text run
    assert runs[0].text == "Standard text, "
    assert not runs[0].bold
    assert not runs[0].italic
    
    # Verify bold text run
    bold_run = [r for r in runs if r.text == "bold text"][0]
    assert bold_run.bold
    assert not bold_run.italic
    
    # Verify italic text run
    italic_run = [r for r in runs if r.text == "italic text"][0]
    assert not italic_run.bold
    assert italic_run.italic

@pytest.mark.asyncio
async def test_generate_file_native_docx():
    # Verify that docx generation runs successfully and calls R2 upload with correct arguments
    content = "# Title\n## Subtitle\n- First item with **bold** text\nStandard paragraph text."
    
    with patch("app.api.v1.endpoints.chat._upload_generated_file") as mock_upload:
        mock_upload.return_value = "mock_docx_url"
        
        url = await _generate_file_native(
            content=content,
            filename="test_document",
            fmt="docx",
            conversation_id="test_convo",
            user_id="test_user"
        )
        
        assert url == "mock_docx_url"
        mock_upload.assert_called_once()
        args, kwargs = mock_upload.call_args
        assert kwargs["mime_type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert len(kwargs["file_bytes"]) > 0
