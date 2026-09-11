# app/core/agent_tools.py
"""
Agent Tools Definition — Phase 6 Roster (25 tools).

Defines all function tools available to the agent model in Agent Mode / OODA loop:

Core (unchanged from Phase 5):
- WIDGET_TOOLS: visualize__read_me, visualize__show_widget
- search_web, deep_research, fetch_url
- sandbox_ls, sandbox_read, sandbox_write, sandbox_edit
- execute_code, terminal
- generate_image, fetch_stock_image
- end_conversation, ask_user_input, weather_fetch

Phase 6 New / Enhanced:
- memory_save  (enhanced: +if_version param for optimistic concurrency)
- memory_recall (unchanged)
- memory_edit   (new: surgical key-value patch)
- render_options_card  (new: comparison / single-pick / carousel UI card)
- render_step_flow     (new: ordered how-to steps & recipes)
- render_itinerary     (new: day-tabbed travel/event schedule)
- render_map           (new: location pins / routes / POI map)
- render_quiz          (new: interactive quiz & flashcard deck)
- render_translation   (new: side-by-side translation card)
"""

from typing import List, Dict, Any
from app.core.widget_tools import WIDGET_TOOLS

AGENT_TOOLS: List[Dict[str, Any]] = [
    # Two-tool inline widget renderer (read_me + show_widget)
    *WIDGET_TOOLS,
    {
        "type": "function",
        "name": "search_web",
        "description": (
            "Search the web for current, real-time information. "
            "Call this for a SINGLE, focused lookup. "
            "For anything time-sensitive (news, prices, laws, releases, scores), "
            "include the current year in the query — e.g. 'Nigeria tax reform 2026'. "
            "AFTER searching: if a result looks central to the answer but the snippet "
            "is thin, follow up with fetch_url on that result's URL to read the page. "
            "TRUST PRIORITY: favour wire services and official bodies (Reuters, AP, "
            "BBC, UEFA/league/club sites for sports, Bloomberg/FT for markets) that "
            "appear in the results; for scores and breaking figures, confirm across "
            "two trusted sources before stating them. "
            "DUTY: cite web-sourced claims with [n](url) markers. "
            "For comparing multiple subjects or researching multiple dimensions at once, "
            "use deep_research instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The precise search query to submit to Google",
                }
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "deep_research",
        "description": (
            "Run multiple parallel web searches simultaneously for complex comparative, "
            "multi-topic, or multi-dimensional queries. "
            "Use this whenever the user asks to compare subjects (phones, products, policies, people), "
            "requests info across multiple dimensions/aspects/ramifications, or needs a structured research report. "
            "Pass a list of 2-6 specific, targeted search strings — one per subject or dimension. "
            "For time-sensitive topics, include the current year in each query. "
            "Results from all queries are merged and returned together. "
            "PREFER this over calling search_web multiple times."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of 2-6 precise, targeted Google search strings",
                    "minItems": 2,
                    "maxItems": 6,
                }
            },
            "required": ["queries"],
        },
    },
    {
        "type": "function",
        "name": "fetch_url",
        "description": (
            "Read the full text content of a specific web page. "
            "WHEN to call: after search_web surfaces a promising result and you need "
            "the page's actual content (not just a snippet); or when the user pastes a "
            "link and asks about its content. "
            "WHEN NOT to call: for PDF/document files (attach or use the document "
            "pipeline instead); for site-wide crawling (call once per page, pick the "
            "most relevant). "
            "DUTY: facts taken from a fetched page must be cited with a [n](url) "
            "marker referencing that page's URL."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The complete http(s) URL of the page to read",
                }
            },
            "required": ["url"],
        },
    },
    {
        "type": "function",
        "name": "memory_save",
        "description": (
            "Persist a durable fact or preference about the user to conversation memory. "
            "WHEN to call: the user states a stable preference, goal, project detail, or "
            "correction worth remembering for later turns (e.g. 'I prefer concise answers', "
            "'my startup is X'). "
            "WHEN NOT to call: credentials, tokens, passwords, card numbers, IDs, or any "
            "sensitive data — a hard privacy gate blocks these regardless. "
            "Keys are short snake_case slugs (e.g. 'tone_preference'); values are one crisp sentence. "
            "OPTIMISTIC CONCURRENCY: pass if_version (the integer version you last read) to "
            "detect concurrent writes. On conflict the gate returns the current value + version "
            "so you can merge and retry in the same turn without bothering the user."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Short snake_case slug identifying the fact",
                },
                "value": {
                    "type": "string",
                    "description": "The fact or preference, one crisp sentence",
                },
                "if_version": {
                    "type": "integer",
                    "description": (
                        "Optional. The version integer of the existing record you last read. "
                        "If provided and the stored version does not match, the write is "
                        "rejected and current state is returned so you can merge and retry."
                    ),
                },
            },
            "required": ["key", "value"],
        },
    },
    {
        "type": "function",
        "name": "memory_recall",
        "description": (
            "Read facts previously saved with memory_save for this conversation. "
            "WHEN to call: at the start of a task where remembered preferences or "
            "facts could change your answer, or when the user asks what you remember. "
            "Call with a specific key when you know it, or no key to dump all saved "
            "facts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Optional specific memory key to recall. Omit to recall all saved facts.",
                }
            },
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "memory_edit",
        "description": (
            "Surgically edit one specific string inside an existing memory value without "
            "rewriting the whole record. Think of it as the memory equivalent of sandbox_edit. "
            "WHEN to call: the user corrects one specific fact, or you need to update a single "
            "detail in a larger stored blob (e.g. update a project name inside a stored brief). "
            "WHEN NOT to call: when you want to replace the whole value — use memory_save instead. "
            "old_str must appear EXACTLY ONCE in the stored value so the patch is unambiguous. "
            "OPTIMISTIC CONCURRENCY: pass if_version to guard against concurrent writes "
            "(same semantics as memory_save.if_version). "
            "Privacy gate applies: new_str containing PII/credentials will be rejected."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "The memory key whose value you want to patch",
                },
                "old_str": {
                    "type": "string",
                    "description": "The exact substring to replace. Must be unique within the stored value.",
                },
                "new_str": {
                    "type": "string",
                    "description": "The replacement string.",
                },
                "if_version": {
                    "type": "integer",
                    "description": (
                        "Optional. Guard against concurrent writes. Same semantics as "
                        "memory_save.if_version."
                    ),
                },
            },
            "required": ["key", "old_str", "new_str"],
        },
    },
    {
        "type": "function",
        "name": "sandbox_ls",
        "description": (
            "List the files in your conversation sandbox workspace, with sizes. "
            "WHEN to call: before reading or overwriting files, when the user refers "
            "to earlier files, or when you need to check what a previous execution "
            "produced. Cheap and safe — call it whenever in doubt."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "subpath": {
                    "type": "string",
                    "description": "Optional subdirectory to list. Omit for the root.",
                }
            },
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "sandbox_read",
        "description": (
            "Read a slice of a text file from your sandbox workspace. "
            "WHEN to call: to inspect a file's content before editing it, verifying a "
            "generated file, or continuing work across turns. Returns up to 4000 bytes "
            "per call with a continuation offset for larger files."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to the sandbox root, e.g. 'report.csv'",
                },
                "offset": {
                    "type": "integer",
                    "description": "Byte offset to start reading from (default 0).",
                },
                "max_bytes": {
                    "type": "integer",
                    "description": "Max bytes to return per call (default 4000, max 16000).",
                },
            },
            "required": ["path"],
        },
    },
    {
        "type": "function",
        "name": "sandbox_write",
        "description": (
            "Write a COMPLETE file into your sandbox workspace. Files written here are "
            "uploaded and surfaced to the user as downloadable artifacts. "
            "QUALITY BAR: write the full file in one call — complete, runnable, no "
            "stubs or placeholders. Never truncate to save tokens. "
            "For binary/chart outputs, use execute_code instead. "
            "AFTER writing large multi-file deliverables, verify with sandbox_read."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to the sandbox root, e.g. 'app/main.py'",
                },
                "content": {
                    "type": "string",
                    "description": "The complete file content (UTF-8 text).",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "type": "function",
        "name": "execute_code",
        "description": (
            "Execute Python, JavaScript (Node.js), or Bash code in a persistent sandbox "
            "with FULL internet access. "
            "STRUCTURE: files persist between calls — read inputs from "
            "`../data/filename.ext` and write outputs there too; anything you save is "
            "automatically uploaded and returned to the user as a download link "
            "(synced to cloud storage). "
            "WHEN to call: run/test code, analyse data, plot charts, fetch live data "
            "in code, convert or process files, perform computation. "
            "QUALITY BAR: generated files must be complete and immediately usable — "
            "never stubs or truncated snippets. "
            "Do NOT use for SVG display (visualize__show_widget) or AI images "
            "(generate_image)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The complete code to execute. Must be self-contained and runnable.",
                },
                "language": {
                    "type": "string",
                    "enum": ["python", "javascript", "bash"],
                    "description": "Programming language of the code snippet",
                },
            },
            "required": ["code", "language"],
        },
    },
    {
        "type": "function",
        "name": "generate_image",
        "description": (
            "Generate a brand-new image using AI (FLUX) from a natural language text description. "
            "Use ONLY when the user wants an AI-synthesised picture from a text prompt — "
            "e.g. 'draw a dragon', 'generate a photo of a sunset', 'create an illustration of X'. "
            "Do NOT call this to render, convert, or execute code. "
            "Do NOT call this for SVG-to-image conversion (use visualize__show_widget instead). "
            "Do NOT call this for data plots or charts (use execute_code with matplotlib instead)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed, descriptive image generation prompt",
                },
                "style": {
                    "type": "string",
                    "enum": ["photorealistic", "illustration", "abstract", "sketch"],
                    "description": "Visual style for the image",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "type": "function",
        "name": "fetch_stock_image",
        "description": (
            "Search free stock photography (Pexels, then Unsplash, then Pixabay) for "
            "real photographic content — website hero/section backgrounds, lifestyle "
            "imagery, real places/people/objects. Returns direct image URLs with "
            "dimensions and photographer attribution; embed chosen photos with "
            "standard markdown image syntax and keep photographer attribution. For "
            "INVENTED or art-directed visuals use generate_image instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for, e.g. 'misty mountain sunrise'",
                },
                "per_page": {
                    "type": "integer",
                    "description": "How many candidates to return (default 6, max 15).",
                },
                "orientation": {
                    "type": "string",
                    "enum": ["landscape", "portrait", "square"],
                    "description": "Preferred orientation (default any).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "terminal",
        "description": (
            "Run ONE shell command in your persistent sandbox workspace (bash), with a "
            "build-grade timeout (~10 min). Use for website build tooling: npm/node "
            "scaffolding and installs (npm create vite@latest, npm install), builds "
            "(npm run build), git, file pipelines. Files persist between calls; outputs "
            "are captured (huge dumps truncated). NOT for long-running servers — no "
            "inbound ports."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to run, e.g. 'npm install && npm run build'",
                },
            },
            "required": ["command"],
        },
    },
    {
        "type": "function",
        "name": "sandbox_edit",
        "description": (
            "Surgical edit (str_replace): replace old_str with new_str inside an "
            "existing sandbox file. old_str must match EXACTLY ONCE — include enough "
            "surrounding context to make it unique. Prefer this over sandbox_write "
            "when changing part of an existing file; use sandbox_read first to get "
            "the exact text (whitespace matters)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to the sandbox root, e.g. 'css/styles.css'",
                },
                "old_str": {
                    "type": "string",
                    "description": "The exact text to replace (must appear exactly once).",
                },
                "new_str": {
                    "type": "string",
                    "description": "The replacement text.",
                },
            },
            "required": ["path", "old_str", "new_str"],
        },
    },
    {
        "type": "function",
        "name": "end_conversation",
        "description": (
            "End the current conversation permanently. Use ONLY after unkind or "
            "abusive treatment continues following your single polite warning — "
            "never for disagreement, hard questions, or frustration alone. Emits a "
            "brief, dignified goodbye; no further messages are processed."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "ask_user_input",
        "description": (
            "Present tappable multiple-choice options to gather a preference before "
            "acting (max once per turn; 1 question, 2-5 options). Use for genuine "
            "preference forks (style, scope, priority) — NOT for things you can "
            "reasonably decide yourself. The user's answer arrives as their next "
            "message; if they type something else, proceed with it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "A single, crisp question.",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2-5 short tappable options.",
                },
                "select_type": {
                    "type": "string",
                    "enum": ["single_select", "multi_select"],
                    "description": "Whether the user picks one or many (default single_select).",
                },
            },
            "required": ["question", "options"],
        },
    },
    {
        "type": "function",
        "name": "weather_fetch",
        "description": (
            "Fetch current weather plus a short forecast for a location (city/region "
            "name; keyless Open-Meteo). Use for weather questions — never guess "
            "weather from training data. Returns condition, temperature, feels-like, "
            "humidity, wind, and daily highs/lows with precipitation chance."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City or place name, e.g. 'Lagos' or 'Cape Town'",
                },
                "days": {
                    "type": "integer",
                    "description": "Forecast days (1-7, default 3).",
                },
            },
            "required": ["location"],
        },
    },

    # ── Phase 6: Consolidated Structured Display Layer ───────────────────────

    {
        "type": "function",
        "name": "render_options_card",
        "description": (
            "WHEN to call: the user is choosing between 2+ named options (products, "
            "approaches, plans, services) that share comparable attributes, OR a single "
            "best recommendation deserves rich visual treatment. "
            "WHEN NOT to call: fewer than 2 comparable attributes (just answer in prose); "
            "options are abstract conceptual tradeoffs without concrete attributes; "
            "you already rendered one this turn (don't stack cards without prose between). "
            "QUALITY BAR: every option must use IDENTICAL attribute label set in IDENTICAL "
            "order so rows align. mode='single_pick' requires exactly 1 option + full "
            "justification blurb. mode='compare' requires 2-3 options. mode='carousel' "
            "allows up to 6 options for browsing. "
            "GOLDEN RULE: never re-list the card's attributes in prose afterward — "
            "the card IS the answer; add only one takeaway sentence."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["single_pick", "compare", "carousel"],
                    "description": "single_pick: one best pick. compare: 2-3 side-by-side. carousel: up to 6 for browsing.",
                },
                "summary": {
                    "type": "string",
                    "description": "One-sentence summary (<15 words) for surfaces that cannot render the card.",
                },
                "options": {
                    "type": "array",
                    "description": "The options to display. All must share the same attribute label set.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "price": {"type": "string", "description": "Optional price string."},
                            "url": {"type": "string", "description": "Optional real URL only — never fabricate."},
                            "blurb": {"type": "string", "description": "Short justification blurb (required for single_pick/carousel)."},
                            "attributes": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string"},
                                        "value": {"type": "string"},
                                    },
                                    "required": ["label", "value"],
                                },
                            },
                        },
                        "required": ["name"],
                    },
                },
            },
            "required": ["mode", "summary", "options"],
        },
    },
    {
        "type": "function",
        "name": "render_step_flow",
        "description": (
            "WHEN to call: the response is an ordered sequence of actions (how-to guide, "
            "tutorial, recipe, troubleshooting checklist). Use this instead of a numbered "
            "markdown list whenever 3-12 steps exist and each step is distinct and actionable. "
            "WHEN NOT to call: fewer than 3 steps; steps are not truly sequential "
            "(use prose or render_options_card for choices); already rendered one this turn. "
            "QUALITY BAR: each step must have a title and body; recipe mode adds ingredient list."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["steps", "recipe"],
                    "description": "steps: generic ordered steps. recipe: includes ingredients list.",
                },
                "title": {
                    "type": "string",
                    "description": "Overall guide/recipe title.",
                },
                "summary": {
                    "type": "string",
                    "description": "One-sentence intro (< 20 words).",
                },
                "ingredients": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Required only for mode=recipe. List of ingredient strings.",
                },
                "steps": {
                    "type": "array",
                    "description": "Ordered list of steps (3-12).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "body": {"type": "string"},
                            "tip": {"type": "string", "description": "Optional pro-tip for this step."},
                        },
                        "required": ["title", "body"],
                    },
                },
            },
            "required": ["mode", "title", "steps"],
        },
    },
    {
        "type": "function",
        "name": "render_itinerary",
        "description": (
            "WHEN to call: the response is a multi-day travel plan, event schedule, "
            "or day-by-day agenda. Produces a tabbed day-view with stops/events and times. "
            "WHEN NOT to call: single-day agenda with fewer than 3 events "
            "(use render_step_flow instead); no temporal/day structure exists. "
            "QUALITY BAR: each day must have a title and at least 2 stops. "
            "Never fabricate prices, hotel names, or real URLs — mark as 'verify before booking'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "destination": {
                    "type": "string",
                    "description": "Primary destination name.",
                },
                "summary": {
                    "type": "string",
                    "description": "One-sentence overview of the itinerary.",
                },
                "days": {
                    "type": "array",
                    "description": "Array of day objects.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "day_label": {"type": "string", "description": "e.g. 'Day 1 — Arrival'"},
                            "stops": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "time": {"type": "string", "description": "Optional time string."},
                                        "name": {"type": "string"},
                                        "description": {"type": "string"},
                                        "tip": {"type": "string"},
                                    },
                                    "required": ["name", "description"],
                                },
                            },
                        },
                        "required": ["day_label", "stops"],
                    },
                },
            },
            "required": ["destination", "summary", "days"],
        },
    },
    {
        "type": "function",
        "name": "render_map",
        "description": (
            "WHEN to call: the response involves geographic locations, directions, "
            "points of interest, or a place lookup — especially after a places search "
            "or weather_fetch returns location context. "
            "WHEN NOT to call: no real geographic data (don't render a map for conceptual "
            "'location' metaphors); data is better shown in a step or options card. "
            "QUALITY BAR: all coordinates must be real — never fabricate lat/lng. "
            "If coordinates are unknown, pass place names and let the frontend geocode."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Map panel title.",
                },
                "center": {
                    "type": "object",
                    "description": "Optional default map center. Leave out to auto-fit pins.",
                    "properties": {
                        "lat": {"type": "number"},
                        "lng": {"type": "number"},
                    },
                },
                "pins": {
                    "type": "array",
                    "description": "List of location pins to show on the map.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "description": {"type": "string"},
                            "lat": {"type": "number", "description": "Real latitude — omit if unknown."},
                            "lng": {"type": "number", "description": "Real longitude — omit if unknown."},
                            "place_name": {"type": "string", "description": "Human-readable place name for geocoding fallback."},
                        },
                        "required": ["label", "place_name"],
                    },
                },
            },
            "required": ["title", "pins"],
        },
    },
    {
        "type": "function",
        "name": "render_quiz",
        "description": (
            "WHEN to call: the user wants to test their knowledge, study for an exam, "
            "create a quiz for others, or practice via flashcards. "
            "WHEN NOT to call: the content is not question-answer structured; "
            "questions don't have clear correct answers. "
            "QUALITY BAR: quiz mode requires at least 3 questions each with 2-5 options "
            "and one marked correct. flashcard mode requires at least 2 cards."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["quiz", "flashcard"],
                    "description": "quiz: multiple-choice with correct answer. flashcard: term/definition flip cards.",
                },
                "title": {
                    "type": "string",
                    "description": "Quiz or deck title.",
                },
                "items": {
                    "type": "array",
                    "description": "Quiz questions or flashcard pairs.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string", "description": "Question text (quiz) or term (flashcard)."},
                            "answer": {"type": "string", "description": "Correct answer text (flashcard back or quiz explanation)."},
                            "options": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Quiz mode only: 2-5 multiple-choice options.",
                            },
                            "correct_index": {
                                "type": "integer",
                                "description": "Quiz mode only: 0-based index of the correct option.",
                            },
                        },
                        "required": ["question", "answer"],
                    },
                },
            },
            "required": ["mode", "title", "items"],
        },
    },
    {
        "type": "function",
        "name": "render_translation",
        "description": (
            "WHEN to call: the user asks to translate text, understand a foreign phrase, "
            "or see a bilingual side-by-side view of a passage. "
            "WHEN NOT to call: the user only wants a quick single-word translation "
            "(just answer in prose); the content is longer than a few paragraphs "
            "(deliver as a file instead). "
            "QUALITY BAR: always include source language and target language labels. "
            "If the source language is ambiguous, detect and label it. "
            "Include pronunciation/romanization only when it adds genuine value "
            "(non-Latin target scripts). "
            "GOLDEN RULE: never re-type the translation in prose — the card is the answer."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source_language": {
                    "type": "string",
                    "description": "Source language name (e.g. 'English').",
                },
                "target_language": {
                    "type": "string",
                    "description": "Target language name (e.g. 'French').",
                },
                "source_text": {
                    "type": "string",
                    "description": "The original text.",
                },
                "translated_text": {
                    "type": "string",
                    "description": "The translated text.",
                },
                "pronunciation": {
                    "type": "string",
                    "description": "Optional romanization or pronunciation guide for non-Latin scripts.",
                },
                "notes": {
                    "type": "string",
                    "description": "Optional linguistic notes (idiom explanations, register, alternatives).",
                },
            },
            "required": ["source_language", "target_language", "source_text", "translated_text"],
        },
    },
]
