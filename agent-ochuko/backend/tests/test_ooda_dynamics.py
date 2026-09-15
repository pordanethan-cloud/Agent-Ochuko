"""
Phase 2/3 — OODA soft-cap dynamics + update_todo checklist (hermetic tests).

Covers:
- get_ooda_dynamics App Config defaults (grace / ceiling multiplier / stall limit)
- THINK iteration cap raise (10 → 25)
- AGENT_STATEFUL_CHAIN default ON (1b shipped to production)
- tool_output_failed heuristic classification
- OODASoftCap: progress extension, stall breaker, hard ceiling backstop
- normalize_todo_list tolerance + status coercion (TodoWrite analog)
- todo_summary rendering
- update_todo present in AGENT_TOOLS + category gate roster
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.agent_config import (
    get_max_iterations,
    get_ooda_dynamics,
    get_stateful_chain_enabled,
)
from app.core.agent_ooda import (
    OODASoftCap,
    normalize_todo_list,
    todo_summary,
    tool_output_failed,
)
from app.core.agent_tools import AGENT_TOOLS
from app.core.category_gate import route_tools


@pytest.fixture
def _config_cache():
    from app.core.config import _CONFIG_CACHE

    saved = dict(_CONFIG_CACHE)
    yield _CONFIG_CACHE
    _CONFIG_CACHE.clear()
    _CONFIG_CACHE.update(saved)


# ── Config: Phase 2 defaults ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_think_cap_raised_to_25(_config_cache):
    _config_cache.pop("MAX_AGENT_ITERS_THINK", None)
    assert await get_max_iterations("think") == 25


@pytest.mark.asyncio
async def test_solve_cap_unchanged(_config_cache):
    _config_cache.pop("MAX_AGENT_ITERS_SOLVE", None)
    assert await get_max_iterations("solve") == 6


@pytest.mark.asyncio
async def test_think_cap_env_overridable(_config_cache):
    _config_cache["MAX_AGENT_ITERS_THINK"] = "40"
    assert await get_max_iterations("think") == 40


@pytest.mark.asyncio
async def test_ooda_dynamics_defaults(_config_cache):
    for key in ("OODA_GRACE_ITERS", "OODA_HARD_CEIL_MULT", "OODA_STALL_LIMIT"):
        _config_cache.pop(key, None)
    dyn = await get_ooda_dynamics()
    assert dyn == {"grace_iters": 3, "hard_ceil_mult": 2, "stall_limit": 2}


@pytest.mark.asyncio
async def test_ooda_dynamics_tunable_and_garbage_safe(_config_cache):
    _config_cache["OODA_GRACE_ITERS"] = "7"
    _config_cache["OODA_STALL_LIMIT"] = "not-a-number"  # garbage → default
    dyn = await get_ooda_dynamics()
    assert dyn["grace_iters"] == 7
    assert dyn["stall_limit"] == 2


# ── Config: Phase 1b shipped ON ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stateful_chain_default_on(_config_cache):
    _config_cache.pop("AGENT_STATEFUL_CHAIN", None)
    assert await get_stateful_chain_enabled() is True


# ── tool_output_failed heuristic ─────────────────────────────────────────────

@pytest.mark.parametrize(
    "out,expected",
    [
        ("search_web error: rate limited", True),
        ("memory_save conflict: {\"conflict\": true}", True),
        ("memory_save blocked: PII detected", True),
        ("terminal failed: exit code 1", True),
        ("execute_code exception: NameError", True),
        ("Memory saved: 'theme' = 'dark'", False),
        ("Search results: ...", False),
        ("Todo list updated (3 items, 0 completed): ...", False),
        ("", False),  # empty output is not failure — just no content
    ],
)
def test_tool_output_failed(out, expected):
    assert tool_output_failed(out) is expected


def test_tool_output_failed_none_is_failure():
    assert tool_output_failed(None) is True


def test_tool_output_error_beyond_head_window_is_success():
    # 'error:' appearing after the 80-char head window does not classify as
    # failure — real result payloads may legitimately contain the word later.
    assert tool_output_failed("ok " + "x" * 100 + " error:") is False


# ── OODASoftCap state machine ────────────────────────────────────────────────

def _cap(nominal=10, **kw):
    return OODASoftCap(nominal_cap=nominal, **kw)


def test_soft_cap_progress_resets_stall():
    cap = _cap()
    cap.note_iteration(["search_web error: boom"])
    assert cap.stall_count == 1 and not cap.forced_close
    cap.note_iteration(["found 5 results: ..."])
    assert cap.stall_count == 0 and cap.progress_count == 1


def test_soft_cap_stall_breaker_trips_after_limit():
    cap = _cap(stall_limit=2)
    cap.note_iteration(["search_web error: a"])
    assert not cap.forced_close
    cap.note_iteration(["fetch_url error: b"])
    assert cap.forced_close


def test_soft_cap_no_extension_while_stalling():
    cap = _cap(nominal=2, stall_limit=5)
    cap.note_iteration(["search_web error: a"])
    assert cap.propose_extension(1, 2) is None  # next_iter == cap but stalled


def test_soft_cap_extension_granted_on_progress_at_cap():
    cap = _cap(nominal=10, grace_iters=3)
    assert cap.propose_extension(3, 10) is None   # budget remains
    cap.note_iteration(["ok results"])
    assert cap.propose_extension(9, 10) == 13     # next_iter(10) == cap → extend
    assert cap.extensions_granted == 1


def test_soft_cap_hard_ceiling_is_absolute_backstop():
    cap = _cap(nominal=10, hard_ceiling=16, grace_iters=3)
    cap.note_iteration(["ok results"])
    assert cap.propose_extension(9, 10) == 13
    cap.note_iteration(["ok results"])
    assert cap.propose_extension(12, 13) == 16    # clamped to ceiling
    cap.note_iteration(["ok results"])
    assert cap.propose_extension(15, 16) is None  # ceiling reached — close now


def test_soft_cap_stall_breaker_beats_extension():
    cap = _cap(nominal=4, stall_limit=2, grace_iters=5)
    cap.note_iteration(["error: a"])
    cap.note_iteration(["error: b"])
    assert cap.forced_close
    assert cap.propose_extension(3, 4) is None


def test_soft_cap_zero_tool_outputs_is_not_progress():
    cap = _cap(stall_limit=1)
    assert cap.note_iteration([]) is False
    assert cap.forced_close  # stall_limit=1 trips immediately


# ── Phase 3: update_todo tool ────────────────────────────────────────────────

def test_update_todo_in_roster():
    names = [t.get("name") for t in AGENT_TOOLS]
    assert "update_todo" in names


def test_update_todo_schema_shape():
    tool = next(t for t in AGENT_TOOLS if t.get("name") == "update_todo")
    assert tool["type"] == "function"
    assert tool["parameters"]["required"] == ["todos"]
    assert tool["parameters"]["properties"]["todos"]["items"]["required"] == [
        "content",
        "status",
    ]
    assert tool["parameters"]["properties"]["todos"]["items"]["properties"]["status"][
        "enum"
    ] == ["pending", "in_progress", "completed"]


def test_gate_includes_update_todo_for_agency():
    cat, tools = route_tools("Can you ask me some questions?", AGENT_TOOLS, iteration=0)
    if cat == "agency":
        assert "update_todo" in [t.get("name") for t in tools]
    # Mid-loop always gets the full roster regardless of category
    _, mid = route_tools("Hello", AGENT_TOOLS, iteration=1)
    assert "update_todo" in [t.get("name") for t in mid]


def test_normalize_todo_list_dict_payload():
    todos = normalize_todo_list(
        {"todos": [
            {"content": "Fetch data", "status": "completed"},
            {"content": "Analyze", "status": "in_progress"},
            {"content": "Write report", "status": "pending"},
        ]}
    )
    assert todos == [
        {"content": "Fetch data", "status": "completed"},
        {"content": "Analyze", "status": "in_progress"},
        {"content": "Write report", "status": "pending"},
    ]


def test_normalize_todo_list_tolerates_junk():
    assert normalize_todo_list(None) == []
    assert normalize_todo_list("nonsense") == []
    assert normalize_todo_list(42) == []
    junk = [
        "plain string item",                     # → pending
        {"task": "task-key alias"},              # alternate content key
        {"content": "bad status", "status": "weird"},  # coerced → pending
        {"content": ""},                         # empty dropped
        17,                                      # non-dict dropped
        {"text": "text-key alias"},              # alternate content key
    ]
    todos = normalize_todo_list(junk)
    assert todos == [
        {"content": "plain string item", "status": "pending"},
        {"content": "task-key alias", "status": "pending"},
        {"content": "bad status", "status": "pending"},
        {"content": "text-key alias", "status": "pending"},
    ]


def test_normalize_todo_list_caps_at_50():
    raw = [{"content": f"item {i}", "status": "pending"} for i in range(80)]
    assert len(normalize_todo_list(raw)) == 50


def test_todo_summary_renders_counts_and_active():
    todos = normalize_todo_list(
        {"todos": [
            {"content": "A", "status": "completed"},
            {"content": "B", "status": "in_progress"},
        ]}
    )
    s = todo_summary(todos)
    assert "2 items" in s and "1 completed" in s
    assert "[completed] A" in s and "[in_progress] B" in s
    assert "Currently active: B" in s


def test_todo_summary_without_active():
    todos = normalize_todo_list([{"content": "A", "status": "pending"}])
    assert "Currently active" not in todo_summary(todos)