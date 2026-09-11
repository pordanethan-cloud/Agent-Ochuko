"""
tests/test_phase6_architecture_upgrade.py
──────────────────────────────────────────
Unit and integration tests for Phase 6: Claude-Grade Parity & Architecture Upgrade.

Covers:
1. Pre-Model Category Gate:
   - Classification of intent (none, research, file_ops, display, memory, media, realtime, agency, all)
   - Route tools dynamic filtering (iteration 0 pruned, iteration > 0 full roster)
   - Zero-schema overhead for 'none' intent
2. Memory Guard & Concurrency:
   - Programmatic deterministic PII filter (credit cards, SSNs, credentials, PHI)
   - Blocked memory key slugs
   - Surgical memory edit (apply_memory_edit) with exact single-match invariant
   - Memory version conflict descriptor
3. Roster Parity & Schemas:
   - Full 25-tool roster validation in AGENT_TOOLS
   - All 6 consolidated display card tool schemas present
   - memory_edit tool schema and memory_save if_version parameter
4. Verification Gates:
   - verify_render_card_schema for all 6 render tools
   - Quality bar enforcement (attribute alignment for render_options_card, steps/days/pins/items non-empty)
"""

import os
import sys
import pytest
from typing import Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.category_gate import classify_intent, route_tools, _CATEGORY_TOOLS
from app.core.memory_guard import (
    check_pii,
    apply_memory_edit,
    describe_memory_version_conflict,
)
from app.core.agent_tools import AGENT_TOOLS
from app.core.verification_gates import verification_gates


# ── 1. Pre-Model Category Gate Tests ───────────────────────────────────────────

class TestCategoryGate:

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("hello", "none"),
            ("hi there", "none"),
            ("Good morning", "none"),
            ("thanks a lot", "none"),
            ("what can you do?", "none"),
            ("who are you", "none"),
            ("explain what quantum computing is", "none"),
            ("search for recent news on SpaceX launch", "research"),
            ("look up documentation on FastAPI dependencies", "research"),
            ("fetch this url https://example.com/docs", "research"),
            ("write a python script to parse CSV files", "file_ops"),
            ("run this code in the sandbox", "file_ops"),
            ("open terminal and run pytest", "file_ops"),
            ("compare iphone 16 pro and pixel 9 pro", "display"),
            ("show me a step by step guide to baking bread", "display"),
            ("plan a trip to Tokyo with an itinerary", "display"),
            ("remember that I prefer dark mode in UI", "memory"),
            ("recall my favorite color", "memory"),
            ("generate an image of a cybernetic tiger", "media"),
            ("fetch a stock photo of a coffee cup", "media"),
            ("what is the weather in London right now?", "realtime"),
        ],
    )
    def test_classify_intent_known_categories(self, query: str, expected: str):
        result = classify_intent(query)
        assert result == expected, f"Query '{query}' expected '{expected}' but got '{result}'"

    def test_classify_intent_empty(self):
        assert classify_intent("") == "none"
        assert classify_intent("   ") == "none"

    def test_classify_intent_ambiguous_defaults_to_all(self):
        # A complex query with conflicting / multi-category signals falls back safely to 'all'
        query = "search for the weather and write a script to save it into memory"
        assert classify_intent(query) == "all"

    def test_route_tools_iteration_zero_conversational(self):
        cat, tools = route_tools("Hello, how are you today?", AGENT_TOOLS, iteration=0)
        assert cat == "none"
        assert tools == []

    def test_route_tools_iteration_zero_filtered_realtime(self):
        cat, tools = route_tools("What's the weather in Seattle?", AGENT_TOOLS, iteration=0)
        assert cat == "realtime"
        tool_names = [t["name"] for t in tools]
        assert "weather_fetch" in tool_names
        # Ensure other heavier schemas are pruned out to save tokens
        assert "sandbox_write" not in tool_names
        assert "execute_code" not in tool_names
        assert "render_options_card" not in tool_names

    def test_route_tools_iteration_zero_filtered_research(self):
        cat, tools = route_tools("Search the web for python 3.14 release notes", AGENT_TOOLS, iteration=0)
        assert cat == "research"
        tool_names = [t["name"] for t in tools]
        assert "search_web" in tool_names
        assert "deep_research" in tool_names
        assert "fetch_url" in tool_names
        assert "weather_fetch" not in tool_names

    def test_route_tools_mid_loop_always_gives_full_roster(self):
        # Iteration > 0 must never prune tools
        cat, tools = route_tools("Hello", AGENT_TOOLS, iteration=1)
        assert cat == "all"
        assert len(tools) == len(AGENT_TOOLS)


# ── 2. Memory Guard & Optimistic Concurrency Tests ────────────────────────────

class TestMemoryGuard:

    def test_check_pii_clean_preference(self):
        is_clean, reason = check_pii("ui_theme", "User prefers dark mode with high contrast.")
        assert is_clean is True
        assert reason is None

    @pytest.mark.parametrize(
        "key,value",
        [
            ("card_info", "My card is 4532-1234-5678-9012 expiring next year"),
            ("payment", "Debit PAN: 5412 7512 3412 3456"),
            ("identity", "SSN is 000-12-3456 please keep safe"),
            ("login", "password: SuperSecretPassword123!"),
            ("token_store", "api_key=sk-proj-abc123456789xyz"),
            ("health_record", "Patient has HIV diagnosis from 2021"),
            ("passport_val", "Passport number is AB1234567"),
        ],
    )
    def test_check_pii_blocked_patterns(self, key: str, value: str):
        is_clean, reason = check_pii(key, value)
        assert is_clean is False
        assert reason is not None
        assert "blocked" in reason.lower()

    @pytest.mark.parametrize("key", ["password", "ssn", "credit_card", "api_key", "iban"])
    def test_check_pii_blocked_key_slugs(self, key: str):
        is_clean, reason = check_pii(key, "something generic")
        assert is_clean is False
        assert "blocked memory key list" in reason.lower()

    def test_apply_memory_edit_success(self):
        current = "User prefers light mode and Python for backend development."
        ok, patched = apply_memory_edit(current, "light mode", "dark mode")
        assert ok is True
        assert patched == "User prefers dark mode and Python for backend development."

    def test_apply_memory_edit_not_found(self):
        current = "User prefers Python."
        ok, err = apply_memory_edit(current, "Rust", "Go")
        assert ok is False
        assert "not found" in err.lower()

    def test_apply_memory_edit_ambiguous_multiple_occurrences(self):
        current = "apple banana apple orange"
        ok, err = apply_memory_edit(current, "apple", "grape")
        assert ok is False
        assert "multiple times" in err.lower()

    def test_apply_memory_edit_empty_old_str(self):
        ok, err = apply_memory_edit("some text", "", "new")
        assert ok is False
        assert "cannot be empty" in err.lower()

    def test_describe_memory_version_conflict(self):
        conflict = describe_memory_version_conflict(
            key="user_goal",
            expected_version=2,
            actual_version=3,
            current_value="Goal: Ship Agent Ochuko Phase 6",
        )
        assert conflict["conflict"] is True
        assert conflict["key"] == "user_goal"
        assert conflict["expected_version"] == 2
        assert conflict["actual_version"] == 3
        assert "Goal: Ship Agent Ochuko Phase 6" in conflict["current_value"]


# ── 3. Roster Parity & Tool Schema Invariants ─────────────────────────────────

class TestToolRosterParity:

    def test_total_roster_count_is_25(self):
        # 18 base tools + 1 memory_edit + 6 render display cards = 25 tools
        assert len(AGENT_TOOLS) == 25, f"Expected 25 tools, got {len(AGENT_TOOLS)}"

    def test_all_expected_tools_registered(self):
        expected_tools = {
            # UI & Widgets
            "visualize__read_me",
            "visualize__show_widget",
            "render_options_card",
            "render_step_flow",
            "render_itinerary",
            "render_map",
            "render_quiz",
            "render_translation",
            # Research
            "search_web",
            "deep_research",
            "fetch_url",
            # Memory
            "memory_save",
            "memory_recall",
            "memory_edit",
            # File System
            "sandbox_ls",
            "sandbox_read",
            "sandbox_write",
            "sandbox_edit",
            # Execution
            "execute_code",
            "terminal",
            # Visual Media
            "generate_image",
            "fetch_stock_image",
            # Agency
            "ask_user_input",
            # Realtime
            "weather_fetch",
            # Safety
            "end_conversation",
        }
        registered = {t["name"] for t in AGENT_TOOLS}
        missing = expected_tools - registered
        assert not missing, f"Missing tools in AGENT_TOOLS: {missing}"

    def test_memory_save_schema_includes_if_version(self):
        mem_save = next(t for t in AGENT_TOOLS if t["name"] == "memory_save")
        props = mem_save["parameters"]["properties"]
        assert "if_version" in props, "memory_save must support optimistic concurrency 'if_version'"

    def test_memory_edit_schema_definition(self):
        mem_edit = next(t for t in AGENT_TOOLS if t["name"] == "memory_edit")
        params = mem_edit["parameters"]
        assert set(params["required"]) == {"key", "old_str", "new_str"}
        assert "if_version" in params["properties"]


# ── 4. Structured Display Verification Gates Tests ─────────────────────────────

class TestStructuredDisplayVerificationGates:

    # 4.1 render_options_card
    def test_verify_render_options_card_single_pick_success(self):
        payload = {
            "mode": "single_pick",
            "summary": "Best database option for serverless apps.",
            "options": [
                {
                    "name": "Supabase Postgres",
                    "blurb": "Full Postgres capability with row-level security and builtin auth.",
                    "attributes": [
                        {"label": "Type", "value": "Relational"},
                        {"label": "Hosting", "value": "Serverless"},
                    ],
                }
            ],
        }
        ok, err = verification_gates.verify_render_card_schema("render_options_card", payload)
        assert ok is True
        assert err is None

    def test_verify_render_options_card_compare_success(self):
        payload = {
            "mode": "compare",
            "summary": "Comparing TailwindCSS and Vanilla CSS for our UI stack.",
            "options": [
                {
                    "name": "TailwindCSS",
                    "attributes": [
                        {"label": "Utility-first", "value": "Yes"},
                        {"label": "Runtime Size", "value": "Zero (purged)"},
                    ],
                },
                {
                    "name": "Vanilla CSS",
                    "attributes": [
                        {"label": "Utility-first", "value": "No (Custom)"},
                        {"label": "Runtime Size", "value": "Minimal"},
                    ],
                },
            ],
        }
        ok, err = verification_gates.verify_render_card_schema("render_options_card", payload)
        assert ok is True
        assert err is None

    def test_verify_render_options_card_attribute_alignment_quality_bar(self):
        # Quality bar: Option attributes must have matching label sequences across all options
        payload = {
            "mode": "compare",
            "summary": "Comparing Option A and B",
            "options": [
                {
                    "name": "Option A",
                    "attributes": [
                        {"label": "Speed", "value": "Fast"},
                        {"label": "Cost", "value": "Low"},
                    ],
                },
                {
                    "name": "Option B",
                    "attributes": [
                        {"label": "Cost", "value": "High"},  # Inverted order! Fails alignment
                        {"label": "Speed", "value": "Medium"},
                    ],
                },
            ],
        }
        ok, err = verification_gates.verify_render_card_schema("render_options_card", payload)
        assert ok is False
        assert "alignment mismatch" in err.lower()

    def test_verify_render_options_card_invalid_mode(self):
        payload = {
            "mode": "unsupported_mode",
            "summary": "Invalid mode test",
            "options": [{"name": "A"}],
        }
        ok, err = verification_gates.verify_render_card_schema("render_options_card", payload)
        assert ok is False
        assert "Invalid mode" in err

    # 4.2 render_step_flow
    def test_verify_render_step_flow_success(self):
        payload = {
            "mode": "steps",
            "title": "Deploying your Static Site",
            "summary": "Three quick steps to push live.",
            "steps": [
                {"title": "Build", "body": "Run npm run build to produce dist/"},
                {"title": "Deploy", "body": "Use hosted_sites_deploy to push bundle."},
                {"title": "Verify", "body": "Open preview URL in browser subagent."},
            ],
        }
        ok, err = verification_gates.verify_render_card_schema("render_step_flow", payload)
        assert ok is True
        assert err is None

    def test_verify_render_step_flow_empty_steps(self):
        payload = {
            "mode": "steps",
            "title": "Empty Steps Guide",
            "steps": [],
        }
        ok, err = verification_gates.verify_render_card_schema("render_step_flow", payload)
        assert ok is False
        assert "non-empty 'steps' list" in err

    # 4.3 render_itinerary
    def test_verify_render_itinerary_success(self):
        payload = {
            "destination": "Kyoto, Japan",
            "summary": "3-day cultural tour of ancient shrines and tea gardens.",
            "days": [
                {
                    "day_label": "Day 1: Arashiyama",
                    "stops": [
                        {"name": "Bamboo Grove", "description": "Morning walk through bamboo path."},
                        {"name": "Tenryu-ji", "description": "Zen garden and temple grounds."},
                    ],
                }
            ],
        }
        ok, err = verification_gates.verify_render_card_schema("render_itinerary", payload)
        assert ok is True
        assert err is None

    def test_verify_render_itinerary_missing_destination(self):
        payload = {
            "destination": "",
            "summary": "Missing dest",
            "days": [{"day_label": "Day 1", "stops": [{"name": "A", "description": "B"}]}],
        }
        ok, err = verification_gates.verify_render_card_schema("render_itinerary", payload)
        assert ok is False
        assert "destination" in err

    # 4.4 render_map
    def test_verify_render_map_success(self):
        payload = {
            "title": "London Tech Hubs",
            "pins": [
                {"label": "Campus London", "place_name": "Bonhill St, Shoreditch", "lat": 51.52, "lng": -0.08},
                {"label": "King's Cross Tech Cluster", "place_name": "Pancras Square, London"},
            ],
        }
        ok, err = verification_gates.verify_render_card_schema("render_map", payload)
        assert ok is True
        assert err is None

    def test_verify_render_map_missing_pins(self):
        payload = {"title": "Empty Map", "pins": []}
        ok, err = verification_gates.verify_render_card_schema("render_map", payload)
        assert ok is False
        assert "non-empty 'pins' list" in err

    # 4.5 render_quiz
    def test_verify_render_quiz_success(self):
        payload = {
            "mode": "quiz",
            "title": "Python Concurrency Basics",
            "items": [
                {
                    "question": "Which module provides cooperative multitasking in Python?",
                    "answer": "asyncio",
                    "options": ["asyncio", "multiprocessing", "threading", "queue"],
                    "correct_index": 0,
                }
            ],
        }
        ok, err = verification_gates.verify_render_card_schema("render_quiz", payload)
        assert ok is True
        assert err is None

    def test_verify_render_quiz_flashcard_mode(self):
        payload = {
            "mode": "flashcard",
            "title": "Vocabulary Flashcards",
            "items": [
                {"question": "Ephemeral", "answer": "Lasting for a very short time."},
                {"question": "Idempotent", "answer": "Denoting an operation which produces the same result if applied multiple times."},
            ],
        }
        ok, err = verification_gates.verify_render_card_schema("render_quiz", payload)
        assert ok is True
        assert err is None

    # 4.6 render_translation
    def test_verify_render_translation_success(self):
        payload = {
            "source_language": "English",
            "target_language": "Japanese",
            "source_text": "Good morning, welcome to our workspace.",
            "translated_text": "おはようございます、ワークスペースへようこそ。",
            "pronunciation": "Ohayō gozaimasu, wākusupēsu e yōkoso.",
        }
        ok, err = verification_gates.verify_render_card_schema("render_translation", payload)
        assert ok is True
        assert err is None

    def test_verify_render_translation_missing_fields(self):
        payload = {
            "source_language": "English",
            "target_language": "",
            "source_text": "Hello",
            "translated_text": "Bonjour",
        }
        ok, err = verification_gates.verify_render_card_schema("render_translation", payload)
        assert ok is False
        assert "target_language" in err

    def test_verify_unknown_card_tool(self):
        ok, err = verification_gates.verify_render_card_schema("unknown_card_tool", {})
        assert ok is False
        assert "Unknown render card tool" in err
