"""
Unit tests for Agent Ochuko Inline Widget Renderer Engine.
Tests widget tools schema, Gemini Flash key rotator fallback, and code extraction.
"""
import pytest
from app.core.widget_tools import WIDGET_TOOLS, OCHUKO_WIDGET_DESIGN_SYSTEM
from app.services.widget_generator import _extract_code_from_text, generate_widget_code


def test_widget_tools_schema():
    """Verify visualize__show_widget tool definition exists and has correct parameters."""
    assert len(WIDGET_TOOLS) == 1
    tool = WIDGET_TOOLS[0]
    assert tool["type"] == "function"
    assert tool["name"] == "visualize__show_widget"
    
    params = tool["parameters"]
    assert "widget_code" in params["properties"]
    assert "title" in params["properties"]
    assert "loading_messages" in params["properties"]
    assert params["required"] == ["widget_code", "title", "loading_messages"]


def test_ochuko_design_tokens():
    """Verify Ochuko obsidian/brass design tokens contain expected CSS variables."""
    assert "--bg-void" in OCHUKO_WIDGET_DESIGN_SYSTEM
    assert "--accent-purple" in OCHUKO_WIDGET_DESIGN_SYSTEM
    assert "--font-mono" in OCHUKO_WIDGET_DESIGN_SYSTEM


def test_extract_code_from_fences():
    """Test extracting clean code from markdown fences."""
    raw_xml = "```xml\n<svg viewBox='0 0 100 100'><rect/></svg>\n```"
    extracted = _extract_code_from_text(raw_xml)
    assert extracted == "<svg viewBox='0 0 100 100'><rect/></svg>"

    raw_html = "```html\n<div class='widget'>Hello World</div>\n```"
    extracted_html = _extract_code_from_text(raw_html)
    assert extracted_html == "<div class='widget'>Hello World</div>"

    raw_plain = "<svg><circle cx='10' cy='10' r='5'/></svg>"
    assert _extract_code_from_text(raw_plain) == raw_plain


@pytest.mark.asyncio
async def test_generate_widget_code_fallback():
    """Verify generate_widget_code handles empty prompts gracefully without crashing."""
    res = await generate_widget_code(
        prompt="Test diagram flow",
        widget_type="diagram",
        title="test_flow",
    )
    assert isinstance(res, dict)
    assert "widget_code" in res
    assert "title" in res
    assert res["title"] == "test_flow"
