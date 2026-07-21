# Agent-Ochuko: Inline Widget Renderer — Implementation Plan

> Replicating the `visualize:read_me` + `visualize:show_widget` system from claude.ai

---

## 1. System Architecture Overview

The claude.ai widget system has three distinct layers. You need all three.

```
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 1: System Prompt                                              │
│  • Proactive trigger logic (when to use visuals)                     │
│  • Tool descriptions with usage rules                                │
│  • Design philosophy (no narrating tool calls, etc.)                 │
├─────────────────────────────────────────────────────────────────────┤
│  LAYER 2: Backend (FastAPI)                                          │
│  • Tool definitions in API call                                      │
│  • read_me handler → returns CSS vars + layout rules as text         │
│  • show_widget handler → emits SSE "widget" event to frontend        │
│  • Tool result loop → passes synthetic result back to model          │
├─────────────────────────────────────────────────────────────────────┤
│  LAYER 3: Frontend (React/TypeScript)                                │
│  • SSE consumer parses "widget" event type                           │
│  • WidgetRenderer component (SVG mode + sandboxed HTML mode)         │
│  • Loading state with animated message cycling                       │
│  • Inline insertion into the chat message stream                     │
└─────────────────────────────────────────────────────────────────────┘
```

The key insight: `show_widget` is **not** a normal tool. It doesn't return data for the model — it fires a side-channel SSE event at the frontend and tells the model "done, continue." The rendering is entirely frontend-side.

---

## 2. Backend Changes (FastAPI)

### 2.1 — Tool Definitions

Add these two tools to every API call that goes through the `/chat` or `/stream` endpoint. Place them in your existing `tools` list.

```python
# tools/widget_tools.py

WIDGET_TOOLS = [
    {
        "name": "visualize__read_me",
        "description": (
            "Returns required context for show_widget: CSS variables, color tokens, "
            "typography rules, layout constraints, and examples for the selected "
            "design modules. Call this BEFORE the first show_widget call in any "
            "response. Do NOT narrate or mention this call to the user."
        ),
        "input_schema": {
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
                            "elicitation"
                        ]
                    }
                },
                "platform": {
                    "type": "string",
                    "enum": ["mobile", "desktop", "unknown"],
                    "default": "desktop",
                    "description": "Target rendering platform."
                }
            },
            "required": ["modules"]
        }
    },
    {
        "name": "visualize__show_widget",
        "description": (
            "Renders SVG or HTML inline in the chat. "
            "Auto-detects mode: code starting with '<svg' → SVG mode. "
            "Everything else → HTML mode (supports JS, inline CSS, Tailwind CDN). "
            "ALWAYS call visualize__read_me first. "
            "Never narrate this call. Use a natural preamble like 'Here's a diagram of that flow.'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "widget_code": {
                    "type": "string",
                    "description": (
                        "Raw SVG code (starting with <svg>) or full HTML content. "
                        "For SVG: use CSS variables for colors. viewBox required. "
                        "For HTML: include all CSS inline. No DOCTYPE/html/body tags needed."
                    )
                },
                "title": {
                    "type": "string",
                    "description": (
                        "Short snake_case identifier. Specific enough to disambiguate "
                        "if multiple widgets exist in the conversation. "
                        "e.g. 'auth_flow_diagram', not 'diagram'. Used as download filename."
                    )
                },
                "loading_messages": {
                    "type": "array",
                    "description": "1–4 short loading messages (~5 words each). Be playful unless topic is serious.",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 4
                }
            },
            "required": ["widget_code", "title", "loading_messages"]
        }
    }
]
```

### 2.2 — Design Module Store

Create a module that holds the design token content returned by `read_me`. This is the "style guide baked into instructions" — except in your implementation it lives server-side and gets injected as a tool result.

```python
# tools/design_modules.py

from typing import Optional

# Agent-Ochuko design tokens — brass/obsidian instrument-panel aesthetic
_OCHUKO_BASE_TOKENS = """
## Agent-Ochuko Design System

### CSS Variables (inject into <style> or SVG <defs>)
```css
:root {
  /* Backgrounds */
  --bg-void: #06060a;
  --bg-deep: #0d0d14;
  --bg-surface: #14141e;
  --bg-raised: #1c1c2a;
  --bg-overlay: #232333;

  /* Brass accent palette */
  --brass-core: #b8860b;
  --brass-bright: #d4a832;
  --brass-dim: #7a5a08;
  --brass-whisper: rgba(184, 134, 11, 0.12);
  --brass-glow: rgba(212, 168, 50, 0.25);

  /* Text */
  --text-primary: #e8e0d0;
  --text-secondary: #9a9090;
  --text-muted: #5a5465;
  --text-accent: #d4a832;

  /* Borders */
  --border-subtle: rgba(184, 134, 11, 0.15);
  --border-visible: rgba(184, 134, 11, 0.30);
  --border-strong: rgba(184, 134, 11, 0.55);

  /* Semantic */
  --success: #4a9463;
  --warning: #c4841a;
  --error: #a83232;
  --info: #3a6ea8;

  /* Sizing */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 14px;
  --widget-max-width: 720px;
  --widget-padding: 20px;

  /* Typography */
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
  --font-ui: 'Inter', system-ui, sans-serif;
}
```

### SVG Color Usage
- Background fills: use `var(--bg-surface)` or `var(--bg-raised)`
- Node fills: `var(--bg-raised)` with stroke `var(--border-visible)`
- Primary accent nodes: `var(--brass-whisper)` fill, `var(--brass-core)` stroke
- Text: `var(--text-primary)` for labels, `var(--text-secondary)` for sub-labels
- Connector lines: `var(--border-visible)` or `var(--brass-dim)` for emphasis paths
- SVG background: transparent or `var(--bg-deep)`

### Sizing Rules
- Default viewBox: `0 0 720 400` (desktop), `0 0 380 500` (mobile)
- Minimum node size: 80×32px
- Font sizes: labels 13px, sub-labels 11px, titles 15px
- Stroke widths: 1px subtle, 1.5px default, 2px emphasis

### DO NOT
- Hard-code hex colors — always use CSS vars
- Use white or pure black backgrounds
- Exceed 720px wide on desktop
- Use generic sans-serif fonts without the stack defined above
"""

_DIAGRAM_MODULE = _OCHUKO_BASE_TOKENS + """
## Module: diagram

### Purpose
Flowcharts, architecture diagrams, sequence diagrams, state machines, entity graphs.

### SVG Patterns

**Node shapes:**
- Process/Step: `<rect rx="6"/>` — bg-raised fill, border-visible stroke
- Decision: `<polygon points="..."/>` — diamond shape
- Endpoint: `<rect rx="20"/>` (pill) — brass-whisper fill, brass-core stroke
- Actor/System: `<rect rx="4"/>` with small icon or initials

**Connectors:**
- Arrow: `marker-end="url(#arrow)"` with a small triangular marker in border-visible
- Emphasis path: stroke brass-dim, stroke-width 2
- Dashed/async: `stroke-dasharray="5,4"`

**Reusable defs block (always include):**
```xml
<defs>
  <marker id="arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
    <polygon points="0 0, 8 3, 0 6" fill="var(--border-visible)"/>
  </marker>
  <marker id="arrow-accent" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
    <polygon points="0 0, 8 3, 0 6" fill="var(--brass-dim)"/>
  </marker>
</defs>
```

### Layout Rules
- Left-to-right for sequential flows; top-to-bottom for hierarchies
- Minimum 60px between nodes (center-to-center spacing)
- Group related nodes with a subtle `<rect>` bg container (opacity 0.4, bg-raised, dashed border)
- Add a title text at top-left: 13px, text-muted, uppercase, letter-spacing 2px

### Example skeleton
```svg
<svg viewBox="0 0 720 320" xmlns="http://www.w3.org/2000/svg">
  <style>:root { /* tokens */ }</style>
  <defs><!-- markers --></defs>
  <rect width="720" height="320" fill="var(--bg-deep)"/>
  <text x="20" y="24" font-family="var(--font-ui)" font-size="11" fill="var(--text-muted)" 
        letter-spacing="2" text-transform="uppercase">FLOW TITLE</text>
  <!-- nodes and paths -->
</svg>
```
"""

_CHART_MODULE = _OCHUKO_BASE_TOKENS + """
## Module: chart

### Purpose
Bar charts, line charts, area charts, pie/donut charts, scatter plots, sparklines.

### HTML Mode (preferred for interactive charts)
Use inline `<canvas>` with vanilla JS or embed a minimal Chart.js snippet.
The widget_code should be full HTML with inline `<script>`.

### SVG Mode (static charts)
Draw axes, gridlines, bars/paths manually.

**Axis styling:**
- Axis lines: `var(--border-subtle)`, stroke-width 1
- Gridlines: `var(--border-subtle)`, stroke-dasharray "3,4", opacity 0.5
- Tick labels: 11px, `var(--text-muted)`, font-family var(--font-ui)
- Axis labels: 12px, `var(--text-secondary)`

**Data encoding:**
- Primary series: `var(--brass-core)` / `var(--brass-bright)`
- Secondary series: `var(--info)`, `var(--success)`
- Negative/warning: `var(--error)`, `var(--warning)`
- Area fill: use series color at 15% opacity

**Chart regions:**
- Plot area padding: 48px left, 32px top, 24px right, 40px bottom
- Background: `var(--bg-surface)` with subtle inner border

### HTML Chart Template
```html
<div style="background:var(--bg-surface);padding:20px;border-radius:10px;
            border:1px solid var(--border-subtle);font-family:var(--font-ui)">
  <canvas id="chart" width="680" height="340"></canvas>
  <script>
    /* Chart.js or vanilla canvas drawing */
    /* Use brass-core (#b8860b) as primary color */
    /* Dark grid, transparent background on canvas */
  </script>
</div>
```
"""

_MOCKUP_MODULE = _OCHUKO_BASE_TOKENS + """
## Module: mockup

### Purpose
UI mockups, wireframes, component previews, form layouts, dashboard sketches.

### Approach
Use HTML mode always for mockups. Inline CSS only. No external resources except
Google Fonts if needed (use a <link> tag).

### Styling Rules
- Render as if it's the Agent-Ochuko UI itself
- Use the brass/obsidian token set
- Components: input fields, buttons, cards, nav bars should match the existing app aesthetic
- Show realistic (but fake) data — not "Lorem Ipsum", not "placeholder"
- Include hover states via CSS :hover where possible

### Component Patterns
```css
/* Button */
.btn-primary {
  background: var(--brass-core);
  color: #000;
  border: none;
  border-radius: 6px;
  padding: 8px 18px;
  font-weight: 600;
  cursor: pointer;
}

/* Input */
.input {
  background: var(--bg-raised);
  border: 1px solid var(--border-visible);
  color: var(--text-primary);
  border-radius: 6px;
  padding: 8px 12px;
}

/* Card */
.card {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 16px;
}
```

### Container
Always wrap in a dark background container matching the app:
```html
<div style="background:var(--bg-deep);min-height:300px;padding:20px;
            font-family:var(--font-ui);color:var(--text-primary)">
```
"""

_INTERACTIVE_MODULE = _OCHUKO_BASE_TOKENS + """
## Module: interactive

### Purpose
Calculators, sliders, toggle-based explorers, sorting visualizations, games,
input-driven demos, step-through explainers.

### Technical Rules
- HTML mode only
- All JS inline in a <script> tag at end of body
- No external CDN except allowed ones: Tailwind CDN, Chart.js CDN
- Use vanilla JS or minimal framework via CDN
- All state in JS variables (no localStorage — it doesn't work in sandboxed iframes)
- Widget must be fully functional on first render without user setup

### Interaction Patterns
- Buttons: use --brass-core for primary actions
- Sliders: style with accent-color: var(--brass-core)
- Output displays: monospace font, bg-raised background, brass-bright text for values
- Animations: CSS transitions preferred (transition: all 0.2s ease)

### Error handling
- All interactive elements must handle edge cases gracefully
- Show validation inline, not via alert()
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
  // All logic here
  // Initialize with defaults immediately
</script>
```
"""

_ART_MODULE = _OCHUKO_BASE_TOKENS + """
## Module: art

### Purpose
Decorative illustrations, visual metaphors, abstract compositions, icons, 
ambient visuals, concept art.

### Style Direction
- Geometric precision over organic shapes
- Layered semi-transparent overlaps
- Brass/gold on deep obsidian
- Grain textures via SVG feTurbulence when mood calls for it
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
Complex multi-series visualizations, network graphs, treemaps, heatmaps,
sankey diagrams, geographic overlays.

### Approach
HTML mode with inline D3-style manual SVG generation via JS, OR pure SVG for
simpler multi-panel layouts.

### Data Encoding Rules
- Max 6 distinct colors before using texture/pattern encoding
- Always include a legend if >2 series
- Null/missing data: show as `var(--bg-overlay)` with 45° hatch pattern
- Outliers: highlight with `var(--brass-bright)` ring

### Responsive Handling
Wrap in a div with overflow-x: auto for wide visualizations.
Target 680px max width for inline rendering.

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
Interactive question forms, multi-step wizards, option pickers, preference
selectors — used when gathering structured input from the user before proceeding.

### Rules
- Always present a clear question at top
- Options as styled buttons (not radio inputs)
- Max 4 options per question
- Include a "None of these / Skip" option if ambiguous
- On selection, call sendPrompt(text) to send the answer back to chat:
  ```js
  button.addEventListener('click', () => sendPrompt(`Option selected: ${label}`))
  ```

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

MODULE_REGISTRY = {
    "diagram":      _DIAGRAM_MODULE,
    "chart":        _CHART_MODULE,
    "mockup":       _MOCKUP_MODULE,
    "interactive":  _INTERACTIVE_MODULE,
    "art":          _ART_MODULE,
    "data_viz":     _DATA_VIZ_MODULE,
    "elicitation":  _ELICITATION_MODULE,
}


def get_read_me_result(modules: list[str], platform: str = "desktop") -> str:
    """Returns the concatenated module content for the tool result."""
    parts = []
    platform_note = ""
    if platform == "mobile":
        platform_note = (
            "\n\n## Platform Override: MOBILE\n"
            "Use viewBox '0 0 380 500'. "
            "Increase font sizes by 2px. "
            "Use single-column layouts. "
            "Minimum tap target: 44×44px.\n"
        )
    for mod in modules:
        if mod in MODULE_REGISTRY:
            parts.append(MODULE_REGISTRY[mod])
        else:
            parts.append(f"[Module '{mod}' not found — use base tokens only]")
    return "\n\n---\n\n".join(parts) + platform_note
```

### 2.3 — SSE Streaming Handler

This is the critical piece. You need to intercept `show_widget` tool calls in your streaming loop and emit a special SSE event type instead of the normal `tool_result` flow.

```python
# routes/chat.py  (modify your existing streaming endpoint)

import json
import asyncio
from fastapi import Request
from fastapi.responses import StreamingResponse
from tools.design_modules import get_read_me_result
from tools.widget_tools import WIDGET_TOOLS

async def stream_with_widgets(conversation_id: str, messages: list, system: str):
    """
    Modified streaming generator that handles widget tool calls.
    Inject this into your existing SSE endpoint.
    """
    
    # Merge widget tools with any existing tools
    all_tools = WIDGET_TOOLS + get_existing_tools()  # your current tools
    
    # Agentic loop — runs until no more tool calls
    while True:
        accumulated_tool_calls = {}
        has_tool_use = False
        
        # Stream from Anthropic
        async with anthropic_client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system,
            messages=messages,
            tools=all_tools,
        ) as stream:
            
            async for event in stream:
                
                # ── Text delta ──────────────────────────────────────────────
                if event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        yield f"data: {json.dumps({'type': 'text_delta', 'text': event.delta.text})}\n\n"
                    
                    elif hasattr(event.delta, "partial_json"):
                        # Accumulate tool input JSON
                        tool_id = getattr(event, "index", 0)
                        if tool_id not in accumulated_tool_calls:
                            accumulated_tool_calls[tool_id] = {"json_str": ""}
                        accumulated_tool_calls[tool_id]["json_str"] += event.delta.partial_json
                
                # ── Tool use block start ─────────────────────────────────────
                elif event.type == "content_block_start":
                    if hasattr(event.content_block, "type") and event.content_block.type == "tool_use":
                        idx = event.index
                        accumulated_tool_calls[idx] = {
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                            "json_str": ""
                        }
                        has_tool_use = True
                        
                        # For show_widget: immediately emit loading state to frontend
                        if event.content_block.name == "visualize__show_widget":
                            yield f"data: {json.dumps({'type': 'widget_loading', 'tool_index': idx})}\n\n"
                
                # ── Message stop ─────────────────────────────────────────────
                elif event.type == "message_stop":
                    break
        
        if not has_tool_use:
            break  # No tools called — we're done
        
        # ── Process tool calls ───────────────────────────────────────────────
        tool_results = []
        assistant_content = []  # reconstruct for message history
        
        for idx, call in sorted(accumulated_tool_calls.items()):
            tool_name = call["name"]
            tool_id = call["id"]
            
            try:
                tool_input = json.loads(call["json_str"]) if call["json_str"] else {}
            except json.JSONDecodeError:
                tool_input = {}
            
            assistant_content.append({
                "type": "tool_use",
                "id": tool_id,
                "name": tool_name,
                "input": tool_input
            })
            
            # ── WIDGET: read_me ──────────────────────────────────────────────
            if tool_name == "visualize__read_me":
                modules = tool_input.get("modules", ["diagram"])
                platform = tool_input.get("platform", "desktop")
                result_text = get_read_me_result(modules, platform)
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result_text
                })
                # No SSE event needed — this is purely context injection
            
            # ── WIDGET: show_widget ──────────────────────────────────────────
            elif tool_name == "visualize__show_widget":
                widget_code = tool_input.get("widget_code", "")
                title = tool_input.get("title", "widget")
                loading_messages = tool_input.get("loading_messages", ["Rendering..."])
                
                # Detect SVG vs HTML
                is_svg = widget_code.strip().startswith("<svg")
                
                # Emit the widget SSE event → frontend renders this
                widget_event = {
                    "type": "widget_render",
                    "title": title,
                    "mode": "svg" if is_svg else "html",
                    "code": widget_code,
                    "loading_messages": loading_messages,
                    "tool_index": idx
                }
                yield f"data: {json.dumps(widget_event)}\n\n"
                
                # Give frontend a moment to process (optional)
                await asyncio.sleep(0.05)
                
                # Return success to the model so it can continue generating
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": f"Widget '{title}' rendered successfully in {('SVG' if is_svg else 'HTML')} mode. Continue your response."
                })
            
            # ── All other tools ──────────────────────────────────────────────
            else:
                result = await handle_existing_tool(tool_name, tool_input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": str(result)
                })
        
        # Append assistant turn + tool results to message history
        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})
```

---

## 3. Frontend Changes (React/TypeScript)

### 3.1 — SSE Consumer Update

Modify your existing SSE consumer to handle the new event types.

```typescript
// hooks/useAgentStream.ts  (extend your existing hook)

type SSEEvent =
  | { type: "text_delta"; text: string }
  | { type: "widget_loading"; tool_index: number }
  | { type: "widget_render"; title: string; mode: "svg" | "html"; code: string; loading_messages: string[]; tool_index: number }
  | { type: "done" }
  | { type: "error"; message: string };

interface MessageBlock {
  kind: "text" | "widget";
  // text blocks
  text?: string;
  // widget blocks
  widgetTitle?: string;
  widgetMode?: "svg" | "html";
  widgetCode?: string;
  loadingMessages?: string[];
  widgetReady?: boolean;
}

export function useAgentStream() {
  const [blocks, setBlocks] = useState<MessageBlock[]>([]);
  
  const handleSSEEvent = useCallback((raw: string) => {
    const event: SSEEvent = JSON.parse(raw);
    
    switch (event.type) {
      case "text_delta":
        setBlocks(prev => {
          const last = prev[prev.length - 1];
          if (last?.kind === "text") {
            // Append to existing text block
            return [
              ...prev.slice(0, -1),
              { ...last, text: (last.text ?? "") + event.text }
            ];
          }
          return [...prev, { kind: "text", text: event.text }];
        });
        break;
      
      case "widget_loading":
        // Insert placeholder while widget streams in
        setBlocks(prev => [
          ...prev,
          {
            kind: "widget",
            widgetReady: false,
            loadingMessages: ["Rendering..."],
            widgetTitle: `widget_${event.tool_index}`
          }
        ]);
        break;
      
      case "widget_render":
        setBlocks(prev => {
          // Replace the loading placeholder with the actual widget
          const placeholderIndex = prev.findLastIndex(
            b => b.kind === "widget" && !b.widgetReady
          );
          if (placeholderIndex === -1) {
            // No placeholder found, append new widget block
            return [...prev, {
              kind: "widget",
              widgetTitle: event.title,
              widgetMode: event.mode,
              widgetCode: event.code,
              loadingMessages: event.loading_messages,
              widgetReady: true
            }];
          }
          const updated = [...prev];
          updated[placeholderIndex] = {
            kind: "widget",
            widgetTitle: event.title,
            widgetMode: event.mode,
            widgetCode: event.code,
            loadingMessages: event.loading_messages,
            widgetReady: true
          };
          return updated;
        });
        break;
    }
  }, []);
  
  return { blocks, handleSSEEvent };
}
```

### 3.2 — WidgetRenderer Component

```tsx
// components/WidgetRenderer.tsx

import { useState, useEffect, useRef, useCallback } from "react";

interface WidgetRendererProps {
  title: string;
  mode: "svg" | "html";
  code: string;
  loadingMessages: string[];
  ready: boolean;
}

export function WidgetRenderer({
  title,
  mode,
  code,
  loadingMessages,
  ready
}: WidgetRendererProps) {
  const [loadingMsgIndex, setLoadingMsgIndex] = useState(0);
  const [renderError, setRenderError] = useState<string | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  
  // Cycle through loading messages
  useEffect(() => {
    if (ready) return;
    const interval = setInterval(() => {
      setLoadingMsgIndex(i => (i + 1) % loadingMessages.length);
    }, 800);
    return () => clearInterval(interval);
  }, [ready, loadingMessages]);
  
  // Inject sendPrompt bridge into HTML widgets
  const buildSandboxedHTML = useCallback((rawCode: string): string => {
    const bridge = `
      <script>
        function sendPrompt(text) {
          window.parent.postMessage({ type: 'agent_prompt', text }, '*');
        }
      </script>
    `;
    // Inject before closing body or at the end
    return rawCode.includes("</body>")
      ? rawCode.replace("</body>", `${bridge}</body>`)
      : bridge + rawCode;
  }, []);
  
  // Listen for sendPrompt messages from iframe
  useEffect(() => {
    const handler = (e: MessageEvent) => {
      if (e.data?.type === "agent_prompt") {
        // Route to your existing chat send function
        window.dispatchEvent(new CustomEvent("agent:send_prompt", {
          detail: { text: e.data.text }
        }));
      }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);
  
  if (!ready) {
    return (
      <div className="widget-loading-state">
        <div className="widget-loading-spinner" />
        <span className="widget-loading-msg">
          {loadingMessages[loadingMsgIndex]}
        </span>
      </div>
    );
  }
  
  // ── SVG Mode ────────────────────────────────────────────────────────────
  if (mode === "svg") {
    return (
      <div
        className="widget-container widget-svg"
        data-title={title}
        dangerouslySetInnerHTML={{ __html: sanitizeSVG(code) }}
        onError={() => setRenderError("SVG render failed")}
      />
    );
  }
  
  // ── HTML Mode (sandboxed iframe) ────────────────────────────────────────
  const sandboxed = buildSandboxedHTML(code);
  const blobURL = URL.createObjectURL(
    new Blob([sandboxed], { type: "text/html" })
  );
  
  return (
    <div className="widget-container widget-html" data-title={title}>
      <iframe
        ref={iframeRef}
        src={blobURL}
        title={title}
        sandbox="allow-scripts allow-same-origin allow-forms"
        className="widget-iframe"
        onLoad={() => URL.revokeObjectURL(blobURL)}
        onError={() => setRenderError("HTML widget failed to load")}
      />
      {renderError && (
        <div className="widget-error">{renderError}</div>
      )}
    </div>
  );
}

// Basic SVG sanitizer — removes script tags and on* attributes
function sanitizeSVG(svg: string): string {
  return svg
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/\son\w+="[^"]*"/gi, "")
    .replace(/\son\w+='[^']*'/gi, "");
}
```

### 3.3 — Styles (add to your global CSS or Tailwind config)

```css
/* widget.css */

.widget-container {
  margin: 12px 0;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  background: var(--bg-surface);
  max-width: 720px;
}

.widget-svg {
  padding: 4px;
}

.widget-svg svg {
  width: 100%;
  height: auto;
  display: block;
}

.widget-html .widget-iframe {
  width: 100%;
  min-height: 300px;
  border: none;
  display: block;
  /* Height auto-expands via ResizeObserver below */
}

.widget-loading-state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 20px;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  margin: 12px 0;
}

.widget-loading-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border-visible);
  border-top-color: var(--brass-core);
  border-radius: 50%;
  animation: widget-spin 0.8s linear infinite;
}

@keyframes widget-spin {
  to { transform: rotate(360deg); }
}

.widget-loading-msg {
  font-size: 13px;
  color: var(--text-muted);
  font-family: var(--font-ui);
  transition: opacity 0.3s ease;
}

.widget-error {
  padding: 8px 12px;
  background: rgba(168, 50, 50, 0.1);
  color: var(--error);
  font-size: 12px;
  font-family: var(--font-mono);
  border-top: 1px solid rgba(168, 50, 50, 0.3);
}

/* Download button (optional — appears on hover) */
.widget-container:hover .widget-download-btn {
  opacity: 1;
}

.widget-download-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  opacity: 0;
  transition: opacity 0.2s ease;
  background: var(--bg-raised);
  border: 1px solid var(--border-visible);
  color: var(--text-secondary);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 11px;
  cursor: pointer;
}
```

### 3.4 — Auto-Resize iframe Height

```typescript
// hooks/useIframeAutoResize.ts

export function useIframeAutoResize(iframeRef: React.RefObject<HTMLIFrameElement>) {
  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    
    const resize = () => {
      try {
        const doc = iframe.contentDocument;
        if (doc?.body) {
          iframe.style.height = doc.body.scrollHeight + "px";
        }
      } catch (_) {
        // Cross-origin — can't read, use postMessage instead
      }
    };
    
    // Also listen for height messages from the iframe itself
    const handler = (e: MessageEvent) => {
      if (e.data?.type === "widget_height") {
        iframe.style.height = e.data.height + "px";
      }
    };
    
    iframe.addEventListener("load", resize);
    window.addEventListener("message", handler);
    return () => {
      iframe.removeEventListener("load", resize);
      window.removeEventListener("message", handler);
    };
  }, [iframeRef]);
}
```

Add this to HTML widgets automatically (inject into `buildSandboxedHTML`):
```javascript
// Auto-report height to parent
window.addEventListener('load', () => {
  window.parent.postMessage({ 
    type: 'widget_height', 
    height: document.body.scrollHeight + 40
  }, '*');
});
```

### 3.5 — Message Renderer Integration

```tsx
// components/MessageBubble.tsx  (modify your existing component)

import { WidgetRenderer } from "./WidgetRenderer";

export function MessageBubble({ blocks }: { blocks: MessageBlock[] }) {
  return (
    <div className="message-bubble assistant">
      {blocks.map((block, i) => {
        if (block.kind === "text") {
          return (
            <div key={i} className="message-text">
              <MarkdownRenderer content={block.text ?? ""} />
            </div>
          );
        }
        
        if (block.kind === "widget") {
          return (
            <WidgetRenderer
              key={i}
              title={block.widgetTitle ?? "widget"}
              mode={block.widgetMode ?? "html"}
              code={block.widgetCode ?? ""}
              loadingMessages={block.loadingMessages ?? ["Rendering..."]}
              ready={block.widgetReady ?? false}
            />
          );
        }
        
        return null;
      })}
    </div>
  );
}
```

---

## 4. System Prompt Additions

Add this section to Agent-Ochuko's system prompt. Place it near the tool instructions, not at the top.

```
## Visualization Tools

You have two visualization tools: visualize__read_me and visualize__show_widget.

### When to use (proactively, without being asked)
- "How does X work" → if it has spatial/sequential/systemic structure, use a diagram
- "Compare X vs Y" → if a chart would be clearer than prose, use one
- "Help me design/architect X" → diagram to anchor the conversation
- "Show me", "visualize", "diagram", "chart", "draw", "illustrate" → always use
- Spec descriptions (nouns naming a visual artifact like "comparison table", "state machine", 
  "form layout") → render it
- Educational concepts with structure → diagram without being asked

### When NOT to use
- Text generation tasks (emails, code, essays)
- Numeric lookups or data questions answerable in prose
- Generic factual questions
- Anything where text is the natural answer

### Flow (mandatory)
1. Call visualize__read_me with the relevant module(s) first
2. Call visualize__show_widget with the generated code
3. Never narrate either call ("let me load the diagram module" is forbidden)
4. Use a natural preamble: "Here's a breakdown of that flow." then the tool call

### Multiple widgets
You may call show_widget multiple times in one response. Never stack calls 
back-to-back without prose between them. Each widget gets surrounding context.

### Content safety
Never generate: graphic violence, sexual content, real identifiable people, 
copyrighted characters, brand logos, misinformation visualizations.

### Module selection guide
- diagram: flows, architecture, sequences, state machines
- chart: bars, lines, areas, pies, sparklines
- mockup: UI components, wireframes, form layouts
- interactive: calculators, sliders, step-through explorers
- art: illustrations, decorative visuals, icons
- data_viz: heatmaps, network graphs, treemaps, complex multi-series
- elicitation: question forms, option pickers (use sendPrompt for interaction)
```

---

## 5. Security Checklist

| Risk | Mitigation |
|------|-----------|
| XSS in SVG | `sanitizeSVG()` strips `<script>` and `on*` attrs before `dangerouslySetInnerHTML` |
| Malicious HTML widget | `sandbox="allow-scripts allow-same-origin"` — no top navigation, no cookies, no form submission to external |
| Data exfiltration from iframe | `allow-same-origin` is scoped to blob: URL — no access to parent domain storage |
| Infinite iframe height | `min-height: 300px`, `max-height: 800px` CSS cap, height only updated via postMessage |
| Model injecting prompt into sendPrompt | Sanitize `e.data.text` before dispatching — strip `<`, `>`, limit to 500 chars |
| Tool call flooding | Rate-limit tool calls: max 3 widget renders per conversation turn |

```typescript
// Sanitize sendPrompt input before dispatching
function sanitizePromptText(text: unknown): string {
  if (typeof text !== "string") return "";
  return text
    .slice(0, 500)
    .replace(/[<>]/g, "")
    .trim();
}
```

---

## 6. Implementation Sequence

Execute in this order:

```
Week 1, Day 1-2:  Backend — tool definitions + design_modules.py
Week 1, Day 3-4:  Backend — SSE streaming handler with widget events
Week 1, Day 5:    Backend — test with curl, verify SSE events emit correctly

Week 2, Day 1-2:  Frontend — SSE consumer update (new event types)
Week 2, Day 3:    Frontend — WidgetRenderer component (SVG mode first)
Week 2, Day 4:    Frontend — HTML/iframe mode + sendPrompt bridge
Week 2, Day 5:    Frontend — styles, auto-resize, loading animations

Week 3, Day 1:    System prompt additions
Week 3, Day 2:    End-to-end test: diagram request → read_me → show_widget → render
Week 3, Day 3:    Interactive widget test (elicitation → sendPrompt → chat)
Week 3, Day 4:    Security audit (SVG sanitization, iframe sandbox)
Week 3, Day 5:    Performance check (no layout shift, fast loading state)
```

---

## 7. Test Cases

After implementation, validate with these prompts:

| Prompt | Expected behavior |
|--------|------------------|
| "explain how JWT auth works" | Proactively shows sequence diagram |
| "compare REST vs GraphQL" | Shows comparison table or chart |
| "show me a bar chart of fake sales data" | HTML chart widget |
| "draw me an abstract illustration" | Art module SVG |
| "what should we focus on first?" | Elicitation widget with options → sendPrompt |
| "make me a login form mockup" | HTML mockup widget |
| Multiple questions in one message | Multiple widgets interleaved with prose |

---

## 8. Known Constraints

1. **Tailwind CDN in iframes** — works, but adds ~300ms. Pre-fetch the CDN link in your HTML shell to warm the cache.

2. **Blob URL expiry** — revoke after iframe loads (already handled). Don't store blob URLs in state.

3. **SVG CSS vars in dark/light mode** — your app likely has a theme toggle. Inject the active theme's CSS vars into the SVG `<style>` tag server-side rather than relying on the frontend cascade, since SVGs rendered via `dangerouslySetInnerHTML` may not inherit root vars correctly in all browsers.

4. **Supabase conversation history** — when you save conversations, store widget blocks as `{ type: "widget", title, mode, code }` in your messages JSONB column. On reload, re-render them directly (don't re-call the API).

5. **Mobile viewport** — pass `platform: "mobile"` in `read_me` calls when your frontend detects `window.innerWidth < 640`.
```
