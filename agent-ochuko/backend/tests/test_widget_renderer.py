"""
Unit tests for Agent Ochuko Inline Widget Renderer Engine.
Tests two-tool system schemas (visualize__read_me + visualize__show_widget) and design tokens.
"""
import pytest
import re
from app.core.widget_tools import WIDGET_TOOLS, OCHUKO_WIDGET_DESIGN_SYSTEM


def _extract_code_from_text(raw_text: str) -> str:
    """Extract code from markdown fences if present."""
    match = re.search(r"```(?:xml|html|svg)?\n(.*?)```", raw_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return raw_text.strip()


def test_widget_tools_schema():
    """Verify visualize__read_me and visualize__show_widget tool definitions exist."""
    assert len(WIDGET_TOOLS) == 2
    names = [t["name"] for t in WIDGET_TOOLS]
    assert "visualize__read_me" in names
    assert "visualize__show_widget" in names

    show_tool = next(t for t in WIDGET_TOOLS if t["name"] == "visualize__show_widget")
    params = show_tool["parameters"]
    assert "widget_code" in params["properties"]
    assert "title" in params["properties"]
    assert "loading_messages" in params["properties"]
    assert params["required"] == ["widget_code", "title", "loading_messages"]


def test_ochuko_design_tokens():
    """Verify Ochuko design tokens contain expected CSS variables."""
    assert "--bg-void" in OCHUKO_WIDGET_DESIGN_SYSTEM
    assert "--text-primary" in OCHUKO_WIDGET_DESIGN_SYSTEM
    assert "--border-subtle" in OCHUKO_WIDGET_DESIGN_SYSTEM


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

