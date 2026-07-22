"""
Widget Tools — Two-Tool System for Agent Ochuko.

visualize__read_me  → injects design tokens + module rules into the model as a tool result
visualize__show_widget → emits an SSE widget event to the frontend for inline rendering

The model MUST call read_me before show_widget. read_me carries the full
Ochuko brass/obsidian design system so the model generates correct code the first
time — no fallback code-generation side-cars needed.
"""
from typing import List, Dict, Any

# ─── Base Design Tokens ────────────────────────────────────────────────────────

_OCHUKO_BASE_TOKENS = """
## Agent-Ochuko Premium Design System (Deep Abyssal Teal & Parchment Legal/Institutional Theme)

This design system uses dense, commanding base tones, sophisticated mid-tones, and high-impact accents to signal institutional trust, engineering precision, and luxury credibility.

### CSS Variables (inject into <style> or SVG <defs>)
```css
:root {
  /* Deep & Authoritative Anchors (Backgrounds) */
  --bg-void:     #0D191D; /* Abyssal black-teal */
  --bg-deep:     #1A3038; /* Deep Abyssal Teal base */
  --bg-surface:  #223D47; /* Mid Abyssal surface */
  --bg-raised:   #294954; /* Raised slate-teal */
  --bg-overlay:  #325764; /* Highlight overlay */

  /* Intelligent & Sophisticated Mid-Tones */
  --petroleum-blue: #005F73; /* Modern tech teal */
  --hyper-violet:   #7000FF; /* High-energy engineering violet */
  --oxide-red:      #A26967; /* Muted terracotta red */
  --racing-green:   #2E6F40; /* Historic financial growth green */

  /* High-Impact Credibility Accents */
  --success:         #00A896; /* Deep Persian Mint (successful status) */
  --green-accent:    #00A896;
  --warning:         #FFB703; /* Gallium Gold (precision warnings, warning alerts) */
  --error:           #E63946; /* Crimson Statement (errors/emergency alert red) */
  --orange-accent:   #FF5A00; /* International Orange (CTAs, high-visibility actions) */

  /* Architectural Neutrals & Highlights */
  --text-primary:   #F4F1DE; /* Parchment White (organic off-white for legal/editorial readability) */
  --text-secondary: #E9ECEF; /* Alunite Grey (cool metallic grey for secondary info) */
  --text-muted:     #8e95a2; /* Cool muted silver */
  --text-accent:    #D4AF37; /* Metallic Brass (matte brass for badges, lines, border validation) */

  /* Mapping legacy tokens for backward compatibility */
  --brass-core:     #00A896; /* Persian Mint */
  --brass-bright:   #FFB703; /* Gallium Gold */
  --brass-dim:      #2E6F40; /* Racing Green */
  --brass-whisper:  rgba(0, 168, 150, 0.08);
  --brass-glow:     rgba(0, 168, 150, 0.18);

  /* Borders */
  --border-subtle:  rgba(233, 236, 239, 0.08);
  --border-visible: rgba(233, 236, 239, 0.18);
  --border-strong:  rgba(233, 236, 239, 0.35);

  /* Sizing */
  --radius-sm:      4px;
  --radius-md:      8px;
  --radius-lg:      14px;
  --widget-max-width: 720px;
  --widget-padding: 20px;

  /* Typography */
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
  --font-ui:   'Inter', system-ui, sans-serif;
}
```

### SVG Color Usage & Theme Rules
- **Base Canvas**: Set canvas backgrounds to `#1A3038` (Deep Abyssal Teal) or transparent.
- **Node/Card Fills**: Use `#223D47` or `#294954` with thin borders of `rgba(233, 236, 239, 0.15)`.
- **Text Labels**: Use `#F4F1DE` (Parchment White) for headers and titles to give a tangible, high-end editorial feel. Use `#E9ECEF` (Alunite Grey) for subtexts.
- **Active States / Confirmation Path**: Use `#00A896` (Deep Persian Mint) for success routes or active nodes.
- **CTAs & Highlights**: Use `#FFB703` (Gallium Gold) or `#FF5A00` (International Orange) for attention highlights or precision warning indicators.

### Mandatory SVG Structure
- ALWAYS include a `<style>` block at the top of the `<svg>` with the `:root` CSS variables above.
- Force text colors: `text { fill: #F4F1DE !important; font-family: system-ui, 'Inter', sans-serif; }`
- Always provide explicit `viewBox` (e.g. `viewBox="0 0 760 440"`) and `width="100%"`.

### DO NOT
- **DO NOT** use generic Anthropic/Claude themes (No `#fbf9f5` warm cream, No `#e8e0d0`, No `#d97757` terracotta/peach, and No light grey or warm beige backgrounds).
- **DO NOT** use default stark/sterile white (#ffffff) or pure black (#000000) for components.
- **DO NOT** leave text elements without explicit fill attribute (`fill="#F4F1DE"`).
"""

# ─── Design Modules ────────────────────────────────────────────────────────────

_DIAGRAM_MODULE = _OCHUKO_BASE_TOKENS + """
## Module: diagram

### Purpose
Flowcharts, high-fidelity architecture diagrams, sequence diagrams, state machines, entity graphs.

### SVG Patterns & Premium Styling
To ensure designs look premium and state-of-the-art:
- **Glowing Drop Shadows**: Always define a `<filter id="glow">` or `<filter id="green-shadow">` containing `feDropShadow` or `feGaussianBlur` to give process blocks a green neon depth glow.
- **Dual-Stop Gradients**: Use `<linearGradient>` for process nodes (e.g. grading from deep slate `#16181b` to slate `#0f1113`) and key paths.
- **Node Shapes**: Process nodes must use rounded corners (`rx="10"` or `rx="12"`), a subtle border (`stroke="var(--brass-core)"`), and `filter="url(#glow)"`. Never draw raw flat sharp rectangles.
- **Connectors**: Use curved bezier connectors (`d="M ... C ..."`), never simple jagged straight lines, to represent fluid pipelines.
- **Icons & Metaphors**: Draw small SVG vector shapes or paths representing icons (e.g. lock/key for security, cylinder for database, cloud for Azure) inside process blocks next to labels.

### Reusable defs block (always include):
```xml
<defs>
  <!-- Green neon drop shadow -->
  <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
    <feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="#10b981" flood-opacity="0.15" />
  </filter>
  <!-- Node background gradient -->
  <linearGradient id="node-grad" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%" stop-color="#16181b"/>
    <stop offset="100%" stop-color="#0f1113"/>
  </linearGradient>
  <linearGradient id="accent-grad" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%" stop-color="rgba(34, 197, 94, 0.18)"/>
    <stop offset="100%" stop-color="rgba(34, 197, 94, 0.05)"/>
  </linearGradient>
  <marker id="arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
    <polygon points="0 0, 8 3, 0 6" fill="var(--brass-core)"/>
  </marker>
</defs>
```

### Layout Rules
- Group related services or zones using container blocks with dashed borders and radial gradients (`radialGradient` representing atmospheric lighting).
- Process steps should align cleanly with grid points.

### Example skeleton
```svg
<svg viewBox="0 0 760 400" width="100%" xmlns="http://www.w3.org/2000/svg">
  <style>
    text { fill: #ffffff !important; font-family: system-ui, -apple-system, sans-serif; font-size: 13px; font-weight: 500; }
    .title { font-size: 11px; fill: #8e95a2 !important; letter-spacing: 2px; font-weight: 600; text-transform: uppercase; }
  </style>
  <defs><!-- defs --></defs>
  <rect width="100%" height="100%" fill="#08090a"/>
  <text x="24" y="28" class="title">PIPELINE ARCHITECTURE</text>
  <!-- nodes, curved paths, and icons -->
</svg>
```
"""


_CHART_MODULE = _OCHUKO_BASE_TOKENS + """
## Module: chart

### Purpose
Bar charts, line charts, area charts, pie/donut charts, scatter plots, sparklines.

### HTML Mode (preferred for interactive charts)
Use Chart.js via CDN:
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
The widget_code should be full HTML with inline <script>.

### SVG Mode (static charts)
Draw axes, gridlines, bars/paths manually.

**Axis styling:**
- Axis lines: var(--border-subtle), stroke-width 1
- Gridlines: var(--border-subtle), stroke-dasharray "3,4", opacity 0.5
- Tick labels: 11px, var(--text-muted), font-family var(--font-ui)
- Axis labels: 12px, var(--text-secondary)

**Data encoding:**
- Primary series: var(--brass-core) / var(--brass-bright)
- Secondary series: var(--info), var(--success)
- Negative/warning: var(--error), var(--warning)
- Area fill: series color at 15% opacity

**Chart regions:**
- Plot area padding: 48px left, 32px top, 24px right, 40px bottom
- Background: var(--bg-surface) with subtle inner border

### HTML Chart Template
```html
<div style="background:var(--bg-surface);padding:20px;border-radius:10px;
            border:1px solid var(--border-subtle);font-family:var(--font-ui)">
  <canvas id="chart" width="680" height="340"></canvas>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script>
    /* Chart.js — use brass-core (#b8860b) as primary color */
  </script>
</div>
```
"""

_MOCKUP_MODULE = _OCHUKO_BASE_TOKENS + """
## Module: mockup

### Purpose
UI mockups, wireframes, component previews, form layouts, dashboard sketches.

### Approach
HTML mode always. Inline CSS only. No external resources except Google Fonts if needed.

### Styling Rules
- Render as if it's the Agent-Ochuko UI itself
- Use the brass/obsidian token set
- Components: inputs, buttons, cards, nav bars match the existing app aesthetic
- Show realistic (non-placeholder) data
- Include :hover states via CSS where possible

### Component Patterns
```css
.btn-primary {
  background: var(--brass-core); color: #000;
  border: none; border-radius: 6px; padding: 8px 18px;
  font-weight: 600; cursor: pointer;
}
.input {
  background: var(--bg-raised); border: 1px solid var(--border-visible);
  color: var(--text-primary); border-radius: 6px; padding: 8px 12px;
}
.card {
  background: var(--bg-surface); border: 1px solid var(--border-subtle);
  border-radius: 10px; padding: 16px;
}
```

### Container
Always wrap in dark background matching the app:
```html
<div style="background:var(--bg-deep);min-height:300px;padding:20px;
            font-family:var(--font-ui);color:var(--text-primary)">
```
"""

_INTERACTIVE_MODULE = _OCHUKO_BASE_TOKENS + """
## Module: interactive

### Purpose
Calculators, sliders, toggle explorers, sorting visualizations, step-through explainers.

### Technical Rules
- HTML mode only
- All JS inline in a <script> tag
- Allowed CDNs: Chart.js, Tailwind CDN
- All state in JS variables (no localStorage — doesn't work in sandboxed iframes)
- Widget must be fully functional on first render

### Interaction Patterns
- Buttons: --brass-core for primary actions
- Sliders: accent-color: var(--brass-core)
- Output displays: monospace font, bg-raised background, brass-bright text for values
- Animations: CSS transitions (transition: all 0.2s ease)

### Error handling
- Handle edge cases gracefully; show validation inline (no alert())
- Default to a valid state on load

### Template
```html
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root { /* tokens */ }
  body { background: var(--bg-surface); color: var(--text-primary);
         font-family: var(--font-ui); padding: 20px; }
</style>
<div id="app"><!-- content --></div>
<script>
  // All logic here — initialize with defaults immediately
</script>
```
"""

_ART_MODULE = _OCHUKO_BASE_TOKENS + """
## Module: art

### Purpose
Decorative illustrations, visual metaphors, abstract compositions, icons, concept art.

### Style Direction
- Geometric precision over organic shapes
- Layered semi-transparent overlaps
- Brass/gold on deep obsidian
- Grain textures via SVG feTurbulence when mood calls
- No photorealistic rendering — stylized, vector-clean

### SVG Art Techniques
```xml
<!-- Noise texture overlay -->
<filter id="grain">
  <feTurbulence type="fractalNoise" baseFrequency="0.65" numOctaves="3" stitchTiles="stitch"/>
  <feColorMatrix type="saturate" values="0"/>
  <feBlend in="SourceGraphic" mode="overlay" result="blend"/>
  <feComposite in="blend" in2="SourceGraphic"/>
</filter>

<!-- Glow effect -->
<filter id="brass-glow">
  <feGaussianBlur stdDeviation="4" result="blur"/>
  <feComposite in="SourceGraphic" in2="blur" operator="over"/>
</filter>

<!-- Radial gradient for atmosphere -->
<radialGradient id="atmo" cx="50%" cy="50%" r="60%">
  <stop offset="0%" stop-color="var(--brass-whisper)"/>
  <stop offset="100%" stop-color="transparent"/>
</radialGradient>
```

### Composition Rules
- Odd-number groupings (3, 5 elements)
- Off-center focal points (rule of thirds)
- Depth via opacity layers: foreground 100%, midground 60%, background 25%
- Thin brass hairlines (stroke 0.5–1px) for fine detail
"""

_DATA_VIZ_MODULE = _OCHUKO_BASE_TOKENS + """
## Module: data_viz

### Purpose
Complex multi-series visualizations, network graphs, treemaps, heatmaps, sankey diagrams.

### Approach
HTML mode with inline D3-style manual SVG generation via JS, OR pure SVG for simpler layouts.

### Data Encoding Rules
- Max 6 distinct colors before using texture/pattern encoding
- Always include a legend if >2 series
- Null/missing data: show as var(--bg-overlay) with 45° hatch pattern
- Outliers: highlight with var(--brass-bright) ring

### Responsive Handling
Wrap in a div with overflow-x: auto. Target 680px max width.

### Legend Pattern
```html
<div style="display:flex;gap:16px;margin-top:12px;flex-wrap:wrap">
  <div style="display:flex;align-items:center;gap:6px">
    <div style="width:12px;height:12px;border-radius:2px;background:var(--brass-core)"></div>
    <span style="font-size:12px;color:var(--text-secondary)">Series A</span>
  </div>
</div>
```
"""

_ELICITATION_MODULE = _OCHUKO_BASE_TOKENS + """
## Module: elicitation

### Purpose
Interactive question forms, multi-step wizards, option pickers, preference selectors —
used when gathering structured input from the user before proceeding.

### Rules
- Always present a clear question at top
- Options as styled buttons (not radio inputs)
- Max 4 options per question
- Include a "None of these / Skip" option if ambiguous
- On selection, call sendPrompt(text) to send the answer back to chat

### sendPrompt bridge
```js
button.addEventListener('click', () => sendPrompt(`Option selected: ${label}`))
```
The sendPrompt function is injected automatically by the frontend — do not define it yourself.

### Layout
```html
<div style="background:var(--bg-surface);padding:20px;border-radius:10px;
            border:1px solid var(--border-subtle)">
  <p style="color:var(--text-secondary);font-size:13px;margin-bottom:16px">
    QUESTION TEXT
  </p>
  <div style="display:flex;flex-direction:column;gap:10px">
    <button onclick="sendPrompt('Option A')"
            style="background:var(--bg-raised);border:1px solid var(--border-visible);
                   color:var(--text-primary);padding:12px 16px;border-radius:8px;
                   text-align:left;cursor:pointer;font-size:14px">
      Option A
    </button>
  </div>
</div>
```
"""

# ─── Module Registry ──────────────────────────────────────────────────────────

_MODULE_REGISTRY: Dict[str, str] = {
    "diagram":     _DIAGRAM_MODULE,
    "chart":       _CHART_MODULE,
    "mockup":      _MOCKUP_MODULE,
    "interactive": _INTERACTIVE_MODULE,
    "art":         _ART_MODULE,
    "data_viz":    _DATA_VIZ_MODULE,
    "elicitation": _ELICITATION_MODULE,
}


def get_read_me_result(modules: List[str], platform: str = "desktop") -> str:
    """
    Returns the concatenated design-token + module-rule content for the
    visualize__read_me tool result. Called by the chat.py tool handler.
    """
    parts: List[str] = []
    for mod in modules:
        content = _MODULE_REGISTRY.get(mod)
        if content:
            parts.append(content)
        else:
            parts.append(f"[Module '{mod}' not found — use base tokens only]")

    result = "\n\n---\n\n".join(parts)

    if platform == "mobile":
        result += (
            "\n\n## Platform Override: MOBILE\n"
            "Use viewBox '0 0 380 500'. "
            "Increase font sizes by 2px. "
            "Use single-column layouts. "
            "Minimum tap target: 44×44px.\n"
        )

    return result


# ─── Tool Definitions ─────────────────────────────────────────────────────────

WIDGET_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "name": "visualize__read_me",
        "description": (
            "Returns required context for show_widget: CSS variables, color tokens, "
            "typography rules, layout constraints, and examples for the selected "
            "design modules. Call this BEFORE the first show_widget call in any "
            "response. Do NOT narrate or mention this call to the user."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "modules": {
                    "type": "array",
                    "description": "Which design module(s) to load.",
                    "items": {
                        "type": "string",
                        "enum": [
                            "diagram",
                            "chart",
                            "mockup",
                            "interactive",
                            "art",
                            "data_viz",
                            "elicitation",
                        ],
                    },
                },
                "platform": {
                    "type": "string",
                    "enum": ["mobile", "desktop", "unknown"],
                    "description": "Target rendering platform. Defaults to desktop.",
                },
            },
            "required": ["modules"],
        },
    },
    {
        "type": "function",
        "name": "visualize__show_widget",
        "description": (
            "Renders SVG or HTML inline in the chat. "
            "Auto-detects mode: code starting with '<svg' → SVG mode. "
            "Everything else → HTML mode (supports JS, inline CSS, Chart.js CDN). "
            "ALWAYS call visualize__read_me first. "
            "Never narrate this call. Use a natural preamble like 'Here's a diagram of that flow.'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "widget_code": {
                    "type": "string",
                    "description": (
                        "Raw SVG code (starting with <svg>) or full HTML content. "
                        "For SVG: use CSS variables for colors. viewBox required. "
                        "For HTML: include all CSS inline. No DOCTYPE/html/body tags needed."
                    ),
                },
                "title": {
                    "type": "string",
                    "description": (
                        "Short snake_case identifier. Specific enough to disambiguate "
                        "if multiple widgets exist. e.g. 'auth_flow_diagram'. "
                        "Used as download filename."
                    ),
                },
                "loading_messages": {
                    "type": "array",
                    "description": "1–4 short loading messages (~5 words each). Be playful unless topic is serious.",
                    "items": {"type": "string"},
                },
                "widget_type": {
                    "type": "string",
                    "enum": ["diagram", "chart", "mockup", "interactive", "art", "data_viz", "elicitation"],
                    "description": "Classification for display label in the widget header.",
                },
            },
            "required": ["widget_code", "title", "loading_messages"],
        },
    },
]

OCHUKO_WIDGET_DESIGN_SYSTEM = _OCHUKO_BASE_TOKENS

