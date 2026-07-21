"""
Widget Generator Sub-Routine Service.
Delegates raw SVG/HTML widget code synthesis to Gemini 2.5 Flash (with API key rotation)
and falls back to Azure OpenAI gpt-5.4-nano/mini to ensure near-zero API cost.
"""
import os
import logging
import itertools
from typing import Optional, List, Dict, Any
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# Collect available Gemini API keys for round-robin rotation
_GEMINI_KEYS: List[str] = [
    k for k in [
        os.getenv("GEMINI_API_KEY"),
        os.getenv("GEMINI_API_KEY_2"),
        os.getenv("GEMINI_API_KEY_3"),
        os.getenv("GEMINI_API_KEY_4"),
    ]
    if k and k.strip()
]

# Iterator for round-robin rotation
_KEY_ITERATOR = itertools.cycle(_GEMINI_KEYS) if _GEMINI_KEYS else None


def _get_next_gemini_client() -> Optional[genai.Client]:
    """Returns a Google GenAI client using the next rotated API key."""
    if not _KEY_ITERATOR:
        return None
    api_key = next(_KEY_ITERATOR)
    try:
        return genai.Client(api_key=api_key)
    except Exception as e:
        logger.warning("Failed to initialize Gemini client with rotated key: %s", e)
        return None


async def generate_widget_code(
    prompt: str,
    widget_type: str = "diagram",
    title: str = "widget_output",
    openai_client: Optional[Any] = None,
    nano_deployment: str = "gpt-5.4-nano",
) -> Dict[str, Any]:
    """
    Generates self-contained SVG or HTML code for the requested visual widget.
    Tries Gemini 2.5 Flash key rotator first, falling back to Azure OpenAI gpt-5.4-nano.
    """
    from app.core.widget_tools import OCHUKO_WIDGET_DESIGN_SYSTEM

    system_instruction = (
        "You are an expert Frontend Visualization Generator for Agent Ochuko.\n"
        f"{OCHUKO_WIDGET_DESIGN_SYSTEM}\n"
        "Instructions:\n"
        "1. For diagrams/flowcharts: Generate valid, standalone SVG code starting with '<svg' and ending with '</svg>'. Use viewBox and CSS variables.\n"
        "2. For charts/mockups/interactive tools: Generate clean, standalone HTML code with inline CSS and JS. Include Chart.js (<script src='https://cdn.jsdelivr.net/npm/chart.js'></script>) if making interactive data charts.\n"
        "3. Output ONLY the code snippet inside ```xml or ```html fences. No conversational chatter."
    )

    # 1. Attempt Gemini 2.5 Flash with Rotated Keys
    client = _get_next_gemini_client()
    if client:
        try:
            logger.info("Generating widget code via Gemini 2.5 Flash (rotated key)...")
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"Generate visual widget for task: {prompt}\nWidget Type: {widget_type}\nTitle: {title}",
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2,
                    max_output_tokens=3000,
                ),
            )
            raw_text = response.text or ""
            # Strip fences if present
            clean_code = _extract_code_from_text(raw_text)
            if clean_code:
                return {
                    "widget_code": clean_code,
                    "title": title,
                    "provider": "gemini-2.5-flash",
                }
        except Exception as gemini_err:
            logger.warning("Gemini widget generation failed: %s — attempting OpenAI fallback...", gemini_err)

    # 2. Fallback to Azure OpenAI gpt-5.4-nano / mini
    if openai_client:
        try:
            logger.info("Generating widget code via Azure OpenAI %s fallback...", nano_deployment)
            resp = openai_client.chat.completions.create(
                model=nano_deployment,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": f"Generate visual widget code for: {prompt}"},
                ],
                max_tokens=3000,
                temperature=0.2,
            )
            raw_text = resp.choices[0].message.content or ""
            clean_code = _extract_code_from_text(raw_text)
            if clean_code:
                return {
                    "widget_code": clean_code,
                    "title": title,
                    "provider": nano_deployment,
                }
        except Exception as openai_err:
            logger.error("Azure OpenAI widget fallback failed: %s", openai_err)

    return {
        "widget_code": "",
        "title": title,
        "provider": "none",
    }


def _extract_code_from_text(text: str) -> str:
    """Extracts code block from ```xml, ```html, ```svg, or ``` markdown fences, or returns raw string."""
    text = text.trim() if hasattr(text, "trim") else text.strip()
    if "```" in text:
        lines = text.splitlines()
        code_lines = []
        inside_fence = False
        for line in lines:
            if line.strip().startswith("```"):
                if inside_fence:
                    break
                else:
                    inside_fence = True
                    continue
            if inside_fence:
                code_lines.append(line)
        if code_lines:
            return "\n".join(code_lines).strip()
    return text
