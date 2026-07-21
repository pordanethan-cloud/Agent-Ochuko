"""
Widget Tools Definition & Design Tokens for Agent Ochuko.
Defines `visualize__show_widget` schema and embedded CSS/SVG design tokens.
"""
from typing import Dict, Any, List

# Agent-Ochuko Obsidian & Brass Design System Tokens & Display Techniques
OCHUKO_WIDGET_DESIGN_SYSTEM = """
## Agent-Ochuko Design System (Obsidian HUD Aesthetic)

### CSS Variables:
:root {
  --bg-void: #06060a;
  --bg-deep: #0c0d10;
  --bg-surface: #12151c;
  --bg-raised: #181c26;

  --accent-primary: #8e95a2;
  --accent-purple: #a855f7;
  --accent-indigo: #6366f1;
  --accent-cyan: #06b6d4;
  --accent-emerald: #10b981;
  --accent-amber: #f59e0b;

  --text-primary: #f8fafc;
  --text-secondary: #cbd5e1;
  --text-muted: #64748b;

  --border-subtle: rgba(255, 255, 255, 0.08);
  --border-visible: rgba(255, 255, 255, 0.18);

  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
  --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
}

### DISPLAY TECHNIQUES & MODULE PATTERNS:

1. DIAGRAM MODULE (SVG Mode):
   - Flowcharts, architecture graphs, sequence diagrams, state machines.
   - Nodes: <rect rx="6"/> with bg-raised fill and border-visible stroke.
   - Connectors: Include reusable <defs><marker id="arrow".../></defs> for clean arrow heads.
   - Spacing: Left-to-right or top-to-bottom layout with min 60px node spacing.

2. CHART MODULE (HTML / Canvas Mode):
   - Bar, line, donut, area charts.
   - Include Chart.js script: <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
   - Dark theme styling on transparent background with primary series color #8e95a2 or #a855f7.

3. MOCKUP MODULE (HTML Mode):
   - UI component previews, forms, cards, dashboards.
   - Containers: min-height 280px, background #0c0d10, rounded-xl padding 20px.
   - Realistic data (no 'Lorem Ipsum' or 'placeholder' text).

4. INTERACTIVE MODULE (HTML Mode):
   - Calculators, sliders, sorting demos, step-through explainers.
   - All state in inline JS. Use transition: all 0.2s ease for smooth micro-interactions.

5. ART MODULE (SVG Mode):
   - Abstract visual metaphors, geometric compositions, noise texture filters (<feTurbulence>).

6. DATA VIZ MODULE (HTML/D3 or SVG):
   - Treemaps, heatmaps, sankey diagrams with legend controls. Max width 680px for inline chat alignment.

7. ELICITATION MODULE (HTML Mode):
   - Option picker cards for user selection. Send response via window.parent or sendPrompt hook.
"""

WIDGET_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "name": "visualize__show_widget",
        "description": (
            "Renders interactive visual widgets inline in the chat bubble — including UI mockups, "
            "wireframes, component cards, dashboards, forms, architecture diagrams, and charts.\n"
            "MANDATORY RULE FOR UI MOCKUPS & INTERFACE DESIGNS:\n"
            "Call visualize__show_widget whenever the user asks for a UI mockup, wireframe, dashboard card, "
            "component layout, form, or interface design. NEVER call generate_image for UI mockups or software designs!\n"
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
