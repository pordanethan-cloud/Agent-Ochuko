"""
Widget Tools Definition & Design Tokens for Agent Ochuko.
Defines `visualize__show_widget` schema and embedded CSS/SVG design tokens.
"""
from typing import Dict, Any, List

# Agent-Ochuko Obsidian & Brass Design System Tokens
OCHUKO_WIDGET_DESIGN_SYSTEM = """
## Agent-Ochuko Design System (Obsidian & Brass HUD)

### CSS Variables (Inject into <style> or SVG <defs>):
:root {
  /* Backgrounds */
  --bg-void: #06060a;
  --bg-deep: #0c0d10;
  --bg-surface: #12151c;
  --bg-raised: #181c26;

  /* Accent Palette */
  --accent-purple: #a855f7;
  --accent-indigo: #6366f1;
  --accent-cyan: #06b6d4;
  --accent-emerald: #10b981;
  --accent-amber: #f59e0b;
  --accent-rose: #f43f5e;

  /* Text Colors */
  --text-primary: #f8fafc;
  --text-secondary: #cbd5e1;
  --text-muted: #64748b;

  /* Borders & Glows */
  --border-subtle: rgba(255, 255, 255, 0.08);
  --border-visible: rgba(255, 255, 255, 0.18);
  --border-accent: rgba(168, 85, 247, 0.35);

  /* Typography */
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
  --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
}
"""

WIDGET_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "name": "visualize__show_widget",
        "description": (
            "Renders interactive visual widgets inline in the chat bubble. "
            "Supports dual modes:\n"
            "  1. SVG Mode: Output starting with '<svg' — for architecture diagrams, flowcharts, timelines, & vector graphics.\n"
            "  2. HTML Mode: Complete HTML page with CSS and JS — for interactive calculators, Chart.js graphs, forms, and UI mockups.\n"
            "Rules:\n"
            "- Always use dark theme (#0c0d10 / #12151c) matching Ochuko design system.\n"
            "- Do NOT narrate or announce this tool call. Use a brief natural preamble line.\n"
            "- Provide 1-4 short loading messages describing what is being assembled."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "widget_code": {
                    "type": "string",
                    "description": "Raw SVG XML code (starting with <svg>) or self-contained HTML document with CSS/JS.",
                },
                "title": {
                    "type": "string",
                    "description": "Short unique identifier (snake_case, e.g. 'auth_architecture_diagram'). Used for file download filename.",
                },
                "loading_messages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "1 to 4 short loading messages (~5 words each) displayed while assembling.",
                },
                "widget_type": {
                    "type": "string",
                    "enum": ["diagram", "chart", "mockup", "interactive"],
                    "description": "Classification type of the visual widget.",
                },
            },
            "required": ["widget_code", "title", "loading_messages"],
        },
    }
]
