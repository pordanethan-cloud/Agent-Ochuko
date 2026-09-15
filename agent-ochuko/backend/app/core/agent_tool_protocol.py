"""
Phase 1a/1b — Native tool protocol helpers for the conversational OODA loop.

Kept in a tiny, dependency-free module so the pure helpers are unit-testable
without importing the heavy chat endpoint module.

Background: the loop previously flattened the model's tool calls to text
("[Executed Tool: ...]") and returned results as fake `role: "system"`
messages ("[Tool Output for X]:"). The Responses API instead expects the
assistant turn preserved as `function_call` items with results fed back as
`function_call_output` items keyed by `call_id` — the same structure Claude
uses (tool_use / tool_result blocks). Native items measurably improve model
orientation, keep parallel calls paired, and unlock stateful chaining.
"""

from typing import Any, Dict, List

NATIVE_ITEM_TYPES = ("function_call", "function_call_output")


def is_native_tool_item(msg: Any) -> bool:
    """True if *msg* is a native Responses API tool-protocol input item."""
    return isinstance(msg, dict) and msg.get("type") in NATIVE_ITEM_TYPES


def text_mirror_history(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Renders native function_call / function_call_output history items as plain
    role-based text messages. Used for consumers that do NOT speak the
    Responses tool protocol (deep_research / search_web sub-agents) so they
    still see the tool transcript. Non-native items are returned unchanged
    (same object references).
    """
    mirrored: List[Dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            mirrored.append(m)
            continue
        m_type = m.get("type")
        if m_type == "function_call":
            mirrored.append({
                "role": "assistant",
                "content": f"[Tool Call: {m.get('name')}({m.get('arguments', '')})]",
            })
        elif m_type == "function_call_output":
            mirrored.append({
                "role": "system",
                "content": (
                    f"[Tool Output for call {m.get('call_id', 'unknown')}]:\n"
                    f"{m.get('output', '')}"
                ),
            })
        else:
            mirrored.append(m)
    return mirrored


def collect_chain_batch(
    local_messages: List[Dict[str, Any]], cursor: int
) -> List[Dict[str, Any]]:
    """
    Phase 1b: when stateful chaining is active, the server already holds every
    item before `cursor` (via previous_response_id). Only the new
    function_call_output items produced since the last API call may be sent —
    assistant text and function_call items were generated server-side and are
    already part of the stored response.
    """
    batch: List[Dict[str, Any]] = []
    if cursor < 0:
        cursor = 0
    for m in local_messages[cursor:]:
        if isinstance(m, dict) and m.get("type") == "function_call_output":
            batch.append(m)
    return batch
