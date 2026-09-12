"""
Verification Gates Module for Agent Ochuko.
Performs programmatic output verification after tool executions, sandbox runs, and document edits.
Checks AST syntax, linting, file structure integrity, and output format schemas.
"""
import ast
import json
import logging
import os
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


class VerificationGateError(Exception):
    """Raised when an output fails verification gates."""
    pass


class VerificationGates:
    """Core verification gate pipeline."""

    @staticmethod
    def verify_python_syntax(code: str) -> Tuple[bool, Optional[str]]:
        """Verify Python code syntax via AST parsing."""
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            error_msg = f"Syntax error at line {e.lineno}, col {e.offset}: {e.msg}"
            logger.warning(f"Python verification gate failed: {error_msg}")
            return False, error_msg
        except Exception as e:
            return False, f"AST parse error: {str(e)}"

    @staticmethod
    def verify_document_header(file_path: str) -> Tuple[bool, Optional[str]]:
        """Verify binary document zip/PDF magic byte headers."""
        if not os.path.exists(file_path):
            return False, f"File does not exist: {file_path}"

        ext = os.path.splitext(file_path.lower())[1]
        try:
            with open(file_path, "rb") as f:
                header = f.read(8)

            if ext in [".docx", ".xlsx", ".pptx"]:
                # ZIP header check (PK\x03\x04)
                if not header.startswith(b"PK\x03\x04"):
                    return False, f"Invalid Office document header for {ext} file."
            elif ext == ".pdf":
                # PDF header check (%PDF-)
                if not header.startswith(b"%PDF"):
                    return False, "Invalid PDF document header magic bytes."

            return True, None
        except Exception as e:
            return False, f"Header check error: {str(e)}"

    # ── Delivery gates: verify-after-write ────────────────────────────────────

    @staticmethod
    def verify_written_file(file_path: str) -> Tuple[bool, Optional[str]]:
        """Confirm a claimed file write actually landed on disk with content."""
        if not os.path.exists(file_path):
            return False, f"file does not exist on disk: {file_path}"
        if os.path.getsize(file_path) <= 0:
            return False, "file exists but is empty (0 bytes)"
        return True, None

    @staticmethod
    def verify_relative_links(html_path: str) -> Tuple[bool, Optional[str]]:
        """
        Verify every relative href/src referenced by an HTML file resolves to a
        real sibling file on disk. Catches the multi-page failure mode where a
        page is written but its stylesheet/script/sibling-page files never land.
        External URLs, data URIs, anchors, and inert schemes are ignored.
        """
        import re as _re

        if not os.path.exists(html_path):
            return False, f"file does not exist: {html_path}"

        try:
            with open(html_path, "r", encoding="utf-8", errors="replace") as f:
                html = f.read()
        except Exception as e:
            return False, f"could not read file: {str(e)}"

        if not html.strip():
            return False, "HTML file is empty"

        base_dir = os.path.dirname(os.path.abspath(html_path))
        refs = _re.findall(r'(?:href|src)\s*=\s*["\']([^"\']+)["\']', html, flags=_re.IGNORECASE)
        missing = []
        for ref in refs:
            clean = ref.split("#", 1)[0].split("?", 1)[0].strip()
            if not clean:
                continue
            if clean.lower().startswith(("http://", "https://", "data:", "mailto:", "tel:", "javascript:", "//")):
                continue
            candidate = os.path.normpath(os.path.join(base_dir, clean))
            if not os.path.exists(candidate):
                missing.append(ref)

        if missing:
            return False, (
                f"broken relative link(s) — target files were never written: {sorted(set(missing))}"
            )
        return True, None

    @staticmethod
    def verify_json_schema(payload_str: str, required_keys: List[str]) -> Tuple[bool, Optional[str]]:
        """Verify JSON payload formatting and required schema keys."""
        try:
            data = json.loads(payload_str)
            if not isinstance(data, dict):
                return False, "Output payload is not a JSON object."
            
            missing = [k for k in required_keys if k not in data]
            if missing:
                return False, f"Missing required keys in payload: {missing}"
            
            return True, None
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON string: {e.msg}"


    # ── Phase 5 (D): responsive / interactive-elements gate ────────────────

    @staticmethod
    def verify_responsive_markup(html: str) -> Tuple[bool, Optional[str]]:
        """
        Static gate over generated index.html in agent mode. Fails when the
        INTERACTIVE ELEMENTS CONTRACT is violated: fixed-px widths on buttons
        or anchor CTAs, missing responsive viewport meta, or icon-only buttons
        without aria-label. A compliant page passes.
        """
        if not html or not html.strip():
            return False, "index.html is empty"

        import re as _re
        lower = html.lower()

        # 1. Viewport meta must exist (responsive rendering contract).
        if "<meta name=\"viewport\"" not in lower and "<meta content=" not in lower:
            return False, "missing responsive viewport <meta name='viewport'>"

        # 2. Fixed-px widths on interactive elements break fluid layout.
        tag_re = _re.compile(r"<(button|a)\b[^>]*>", _re.IGNORECASE)
        fixed_px = _re.compile(r"\bwidth\s*:\s*\d+px", _re.IGNORECASE)
        for m in tag_re.finditer(html):
            if fixed_px.search(m.group(0)):
                return False, (
                    "fixed-px width on interactive element "
                    f"({m.group(0)[:80]}...) — use inline-flex + padding, max-width:100%"
                )

        # 3. Icon-only buttons need aria-label.
        for m in tag_re.finditer(html):
            tag = m.group(0)
            if "<button" in tag.lower() and "aria-label" not in tag.lower():
                inner_start = m.end()
                inner_end = html.find("</button>", inner_start)
                inner = html[inner_start:inner_end if inner_end != -1 else inner_start]
                visible_text = _re.sub(r"<[^>]+>", "", inner).strip()
                if not visible_text and ("svg" in inner.lower() or "icon" in tag.lower()):
                    return False, f"icon-only <button> missing aria-label: {tag[:80]}..."

        return True, None

    # ── Phase 6: Consolidated Structured Display Layer verification ──────────

    @staticmethod
    def verify_render_card_schema(tool_name: str, payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Verify the structure, required fields, and quality invariants of the
        6 consolidated display cards: render_options_card, render_step_flow,
        render_itinerary, render_map, render_quiz, render_translation.
        """
        if not isinstance(payload, dict):
            return False, f"Payload for {tool_name} must be a JSON object (dict)."

        if tool_name == "render_options_card":
            mode = payload.get("mode")
            if mode not in ("single_pick", "compare", "carousel"):
                return False, f"Invalid mode '{mode}'. Must be 'single_pick', 'compare', or 'carousel'."
            if not payload.get("summary"):
                return False, "render_options_card requires a non-empty summary."
            options = payload.get("options")
            if not isinstance(options, list) or len(options) == 0:
                return False, "render_options_card requires a non-empty 'options' list."

            if mode == "single_pick" and len(options) != 1:
                return False, f"mode='single_pick' requires exactly 1 option (received {len(options)})."
            if mode == "compare" and not (2 <= len(options) <= 3):
                return False, f"mode='compare' requires 2-3 options (received {len(options)})."
            if mode == "carousel" and not (1 <= len(options) <= 6):
                return False, f"mode='carousel' allows 1 to 6 options (received {len(options)})."

            for idx, opt in enumerate(options):
                if not isinstance(opt, dict) or not opt.get("name"):
                    return False, f"Option #{idx + 1} must be an object with a 'name'."

            # Quality Bar: attribute label set alignment across options
            first_attrs = options[0].get("attributes")
            if first_attrs and isinstance(first_attrs, list):
                first_labels = [a.get("label") for a in first_attrs if isinstance(a, dict) and a.get("label")]
                for idx, opt in enumerate(options[1:], start=2):
                    cur_attrs = opt.get("attributes")
                    if not isinstance(cur_attrs, list):
                        return False, f"Option #{idx} is missing attributes to align with Option #1."
                    cur_labels = [a.get("label") for a in cur_attrs if isinstance(a, dict) and a.get("label")]
                    if cur_labels != first_labels:
                        return False, (
                            f"Attribute label alignment mismatch in Option #{idx}. "
                            f"Expected labels {first_labels}, got {cur_labels}."
                        )

            return True, None

        elif tool_name == "render_step_flow":
            mode = payload.get("mode")
            if mode not in ("steps", "recipe"):
                return False, f"Invalid mode '{mode}'. Must be 'steps' or 'recipe'."
            if not payload.get("title"):
                return False, "render_step_flow requires a non-empty 'title'."
            steps = payload.get("steps")
            if not isinstance(steps, list) or len(steps) == 0:
                return False, "render_step_flow requires a non-empty 'steps' list."
            for idx, s in enumerate(steps):
                if not isinstance(s, dict) or not s.get("title") or not s.get("body"):
                    return False, f"Step #{idx + 1} must be an object containing both 'title' and 'body'."
            if mode == "recipe" and "ingredients" in payload:
                if not isinstance(payload["ingredients"], list):
                    return False, "'ingredients' in recipe mode must be a list."

            return True, None

        elif tool_name == "render_itinerary":
            if not payload.get("destination"):
                return False, "render_itinerary requires a non-empty 'destination'."
            if not payload.get("summary"):
                return False, "render_itinerary requires a non-empty 'summary'."
            days = payload.get("days")
            if not isinstance(days, list) or len(days) == 0:
                return False, "render_itinerary requires a non-empty 'days' list."
            for d_idx, day in enumerate(days):
                if not isinstance(day, dict) or not day.get("day_label"):
                    return False, f"Day #{d_idx + 1} must have a 'day_label'."
                stops = day.get("stops")
                if not isinstance(stops, list) or len(stops) == 0:
                    return False, f"Day #{d_idx + 1} ('{day.get('day_label')}') must have a non-empty 'stops' list."
                for s_idx, stop in enumerate(stops):
                    if not isinstance(stop, dict) or not stop.get("name") or not stop.get("description"):
                        return False, f"Day #{d_idx + 1}, Stop #{s_idx + 1} must have both 'name' and 'description'."

            return True, None

        elif tool_name == "render_map":
            if not payload.get("title"):
                return False, "render_map requires a non-empty 'title'."
            pins = payload.get("pins")
            if not isinstance(pins, list) or len(pins) == 0:
                return False, "render_map requires a non-empty 'pins' list."
            for idx, pin in enumerate(pins):
                if not isinstance(pin, dict) or not pin.get("label") or not pin.get("place_name"):
                    return False, f"Pin #{idx + 1} must have both 'label' and 'place_name'."

            return True, None

        elif tool_name == "render_quiz":
            mode = payload.get("mode")
            if mode not in ("quiz", "flashcard"):
                return False, f"Invalid mode '{mode}'. Must be 'quiz' or 'flashcard'."
            if not payload.get("title"):
                return False, "render_quiz requires a non-empty 'title'."
            items = payload.get("items")
            if not isinstance(items, list) or len(items) == 0:
                return False, "render_quiz requires a non-empty 'items' list."
            for idx, item in enumerate(items):
                if not isinstance(item, dict) or not item.get("question") or not item.get("answer"):
                    return False, f"Item #{idx + 1} must have both 'question' and 'answer'."
                if mode == "quiz" and "options" in item:
                    if not isinstance(item["options"], list) or len(item["options"]) < 2:
                        return False, f"Quiz item #{idx + 1} options must be a list with at least 2 choices."

            return True, None

        elif tool_name == "render_translation":
            for field in ("source_language", "target_language", "source_text", "translated_text"):
                val = payload.get(field)
                if not val or not str(val).strip():
                    return False, f"render_translation requires non-empty '{field}'."

            return True, None

        elif tool_name == "render_sports_card":
            if not payload.get("home_team") or not str(payload.get("home_team")).strip():
                return False, "render_sports_card requires a non-empty 'home_team'."
            if not payload.get("away_team") or not str(payload.get("away_team")).strip():
                return False, "render_sports_card requires a non-empty 'away_team'."
            if payload.get("home_score") is None or str(payload.get("home_score")).strip() == "":
                return False, "render_sports_card requires 'home_score'."
            if payload.get("away_score") is None or str(payload.get("away_score")).strip() == "":
                return False, "render_sports_card requires 'away_score'."
            if not payload.get("status") or not str(payload.get("status")).strip():
                return False, "render_sports_card requires 'status' (e.g. '45\' + 3\'', 'FT', 'LIVE', etc.)."
            if not payload.get("competition") or not str(payload.get("competition")).strip():
                return False, "render_sports_card requires 'competition'."
            events = payload.get("events")
            if events is not None:
                if not isinstance(events, list):
                    return False, "render_sports_card 'events' must be a list."
                for idx, ev in enumerate(events):
                    if not isinstance(ev, dict):
                        return False, f"Event #{idx + 1} must be an object."
                    if not ev.get("team") or ev.get("team") not in ("home", "away"):
                        return False, f"Event #{idx + 1} must have 'team' ('home' or 'away')."
                    if not ev.get("player"):
                        return False, f"Event #{idx + 1} must have a 'player' name."
                    if not ev.get("minute"):
                        return False, f"Event #{idx + 1} must have a 'minute' (e.g. '7\'')."

            # Server-side sanitization: purge empty, zero-filled, or dummy stats objects
            stats = payload.get("stats")
            if isinstance(stats, dict):
                has_meaningful_stats = False
                for k, v in stats.items():
                    if isinstance(v, (list, tuple)):
                        if any(isinstance(x, (int, float)) and x > 0 for x in v):
                            has_meaningful_stats = True
                            break
                    elif isinstance(v, (int, float)) and v > 0:
                        has_meaningful_stats = True
                        break
                if not has_meaningful_stats:
                    payload.pop("stats", None)

            return True, None

        return False, f"Unknown render card tool: '{tool_name}'"


# Global instance
verification_gates = VerificationGates()
