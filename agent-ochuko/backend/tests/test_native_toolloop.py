"""
Phase 1a/1b — Native tool protocol + stateful chaining (hermetic tests).

Covers:
- AGENT_NATIVE_TOOLLOOP / AGENT_STATEFUL_CHAIN config flag semantics
- normalize_responses_message pass-through for native tool items
- collect_chain_batch cursor semantics (Phase 1b chaining input)
- text_mirror_history rendering for non-Responses consumers
- parallel function_call / function_call_output pairing (loop append logic)

Mirrors the hermetic conventions of test_ultra_upgrade.py (local
_config_cache fixture, saved/restored around each test).
"""
import pytest

from app.core.agent_config import (
    get_native_toolloop_enabled,
    get_stateful_chain_enabled,
)
from app.core.agent_tool_protocol import (
    collect_chain_batch,
    is_native_tool_item,
    text_mirror_history,
)


@pytest.fixture
def _config_cache():
    from app.core.config import _CONFIG_CACHE

    saved = dict(_CONFIG_CACHE)
    yield _CONFIG_CACHE
    _CONFIG_CACHE.clear()
    _CONFIG_CACHE.update(saved)


# ── Config flags ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_native_toolloop_default_on(_config_cache):
    _config_cache.pop("AGENT_NATIVE_TOOLLOOP", None)
    assert await get_native_toolloop_enabled() is True


@pytest.mark.asyncio
async def test_native_toolloop_explicit_off(_config_cache):
    for off_val in ("false", "0", "off", "no"):
        _config_cache["AGENT_NATIVE_TOOLLOOP"] = off_val
        assert await get_native_toolloop_enabled() is False, off_val


@pytest.mark.asyncio
async def test_stateful_chain_default_on(_config_cache):
    # Phase 1b shipped to production: default ON (one-shot degrade built in).
    _config_cache.pop("AGENT_STATEFUL_CHAIN", None)
    assert await get_stateful_chain_enabled() is True


@pytest.mark.asyncio
async def test_stateful_chain_explicit_off(_config_cache):
    for off_val in ("false", "0", "off", "no"):
        _config_cache["AGENT_STATEFUL_CHAIN"] = off_val
        assert await get_stateful_chain_enabled() is False, off_val


# ── normalize_responses_message pass-through ─────────────────────────────────

def test_normalize_passes_native_items_untouched():
    from app.api.v1.endpoints.chat import normalize_responses_message

    fc = {"type": "function_call", "call_id": "call_1", "name": "search_web", "arguments": "{}"}
    fco = {"type": "function_call_output", "call_id": "call_1", "output": "ok"}
    # Same object returned — no role coercion, no content collapse
    assert normalize_responses_message(fc) is fc
    assert normalize_responses_message(fco) is fco




# ── Phase 1b chaining batch ──────────────────────────────────────────────────

def _native_history():
    return [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "Let me check."},
        {"type": "function_call", "call_id": "c1", "name": "t1", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "c1", "output": "o1"},
        {"type": "function_call", "call_id": "c2", "name": "t2", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "c2", "output": "o2"},
    ]


def test_collect_chain_batch_only_outputs():
    h = _native_history()
    # cursor 0 / 2: every output from the cursor onward is returned —
    # statically both exist; at runtime later items simply aren't appended yet
    assert collect_chain_batch(h, 0) == [h[3], h[5]]
    assert collect_chain_batch(h, 2) == [h[3], h[5]]
    # after second send (cursor 4) → output c2 only
    assert collect_chain_batch(h, 4) == [h[5]]
    # everything sent → empty batch
    assert collect_chain_batch(h, 6) == []


def test_collect_chain_batch_negative_cursor_clamped():
    h = _native_history()
    assert collect_chain_batch(h, -5) == [h[3], h[5]]


def test_chained_iteration_sequence():
    """Simulates two chained iterations with incremental history growth."""
    local = [{"role": "user", "content": "q"}]
    # Iteration 0: full replay of local (cursor = len at send time)
    cursor = len(local)  # 1
    # Tool turn 1 appends call + output
    local.append({"type": "function_call", "call_id": "c1", "name": "t1", "arguments": "{}"})
    out1 = {"type": "function_call_output", "call_id": "c1", "output": "o1"}
    local.append(out1)
    # Chained iteration 1 sends ONLY the new output
    assert collect_chain_batch(local, cursor) == [out1]
    cursor = len(local)  # 3 after the chained send
    # Tool turn 2 appends call + output
    local.append({"type": "function_call", "call_id": "c2", "name": "t2", "arguments": "{}"})
    out2 = {"type": "function_call_output", "call_id": "c2", "output": "o2"}
    local.append(out2)
    # Chained iteration 2 sends only output c2 (never replays o1)
    assert collect_chain_batch(local, cursor) == [out2]
    cursor = len(local)  # 5
    assert collect_chain_batch(local, cursor) == []


# ── Text mirror for non-Responses consumers ──────────────────────────────────

def test_text_mirror_history_renders_native_as_text():
    h = [
        {"role": "user", "content": "q"},
        {"type": "function_call", "call_id": "c1", "name": "search_web", "arguments": '{"query": "x"}'},
        {"type": "function_call_output", "call_id": "c1", "output": "result text"},
        {"role": "assistant", "content": "final"},
    ]
    m = text_mirror_history(h)
    assert m[0] is h[0] and m[3] is h[3]  # non-native items untouched
    assert m[1] == {"role": "assistant", "content": '[Tool Call: search_web({"query": "x"})]'}
    assert "[Tool Output for call c1]" in m[2]["content"]
    assert "result text" in m[2]["content"]
    # Original history is never mutated
    assert h[1]["type"] == "function_call"
    assert h[2]["type"] == "function_call_output"


def test_text_mirror_history_tolerates_junk():
    assert text_mirror_history([]) == []
    junk = ["not-a-dict", 42, {"role": "user", "content": "ok"}]
    m = text_mirror_history(junk)  # type: ignore[arg-type]
    assert m[0] == "not-a-dict" and m[1] == 42 and m[2] is junk[2]


def test_is_native_tool_item():
    assert is_native_tool_item({"type": "function_call"}) is True
    assert is_native_tool_item({"type": "function_call_output"}) is True
    assert is_native_tool_item({"role": "assistant", "content": "x"}) is False
    assert is_native_tool_item("string") is False
    assert is_native_tool_item(None) is False


# ── Parallel call pairing (mirrors loop append logic) ────────────────────────

def test_parallel_call_pairing_is_call_id_safe():
    calls = [
        {"id": "fc_a", "call_id": "fc_a", "name": "t1", "arguments": "{}"},
        {"id": "fc_b", "call_id": "fc_b", "name": "t2", "arguments": "{}"},
    ]
    outputs = ["out1", "out2"]
    local = []
    # Assistant text + function_call items (loop append, native branch)
    local.append({"role": "assistant", "content": "Working on it."})
    for tc in calls:
        local.append({
            "type": "function_call",
            "call_id": tc.get("call_id") or tc["id"],
            "name": tc["name"],
            "arguments": tc["arguments"],
        })
    # function_call_output items (loop feedback, native branch)
    for tc, t_out in zip(calls, outputs):
        local.append({
            "type": "function_call_output",
            "call_id": tc.get("call_id") or tc["id"],
            "output": t_out if isinstance(t_out, str) else str(t_out),
        })

    native_calls = [m for m in local if m.get("type") == "function_call"]
    native_outs = [m for m in local if m.get("type") == "function_call_output"]
    assert [c["call_id"] for c in native_calls] == ["fc_a", "fc_b"]
    assert [o["call_id"] for o in native_outs] == ["fc_a", "fc_b"]
    assert [o["output"] for o in native_outs] == ["out1", "out2"]
    # Every call has exactly one matching output
    assert {c["call_id"] for c in native_calls} == {o["call_id"] for o in native_outs}
    # No legacy text flattening leaked into native mode
    assert not any("[Executed Tool:" in str(m.get("content", "")) for m in local)

def test_normalize_legacy_behavior_unchanged():
    from app.api.v1.endpoints.chat import normalize_responses_message

    assert normalize_responses_message({"role": "user", "content": "hello"}) == {
        "role": "user",
        "content": "hello",
    }
    # A message with no role/content still behaves as before (coerced user, "")
    assert normalize_responses_message({}) == {"role": "user", "content": ""}
