"""
Phase 9 (blackboard scratchpad working memory) — unit tests.

Covers:
- append_scratchpad_entry: shape, capping, eviction, no-op contract.
- scratchpad_digest: prompt-injection digest, empty/malformed safety.
- AgentTask.scratchpad: model default + persistence round-trip.
- AgentContextCompressor: digest injection into step + synthesis payloads.
- agent_task_manager wiring: save_state key, _write_note call sites.
"""
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.agent_task_models import (  # noqa: E402
    AgentTask,
    append_scratchpad_entry,
    scratchpad_digest,
    SCRATCHPAD_MAX_ENTRIES,
    SCRATCHPAD_MAX_CONTENT,
)
from app.services.hybrid_memory import AgentContextCompressor  # noqa: E402

_TASK_MANAGER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "core", "agent_task_manager.py",
)


class TestAppendScratchpadEntry:
    """Pure-function contract for the blackboard append."""

    def test_basic_entry_shape(self):
        board = append_scratchpad_entry({}, "fact", "repo uses bun", step_index=2)
        assert len(board["entries"]) == 1
        e = board["entries"][0]
        assert e["kind"] == "fact"
        assert e["content"] == "repo uses bun"
        assert e["step_index"] == 2
        assert e["id"].startswith("fact-")
        assert e["created_at"]

    def test_empty_content_is_noop(self):
        assert append_scratchpad_entry({}, "fact", "   ") == {}

    def test_none_content_is_noop(self):
        assert append_scratchpad_entry({}, "fact", None) == {}

    def test_content_truncated_to_cap(self):
        board = append_scratchpad_entry({}, "fact", "x" * (SCRATCHPAD_MAX_CONTENT + 100))
        assert len(board["entries"][0]["content"]) == SCRATCHPAD_MAX_CONTENT

    def test_oldest_evicted_beyond_cap(self):
        board = {}
        for i in range(SCRATCHPAD_MAX_ENTRIES + 5):
            append_scratchpad_entry(board, "fact", f"note {i}")
        entries = board["entries"]
        assert len(entries) == SCRATCHPAD_MAX_ENTRIES
        assert entries[0]["content"] == f"note {5}"
        assert entries[-1]["content"] == f"note {SCRATCHPAD_MAX_ENTRIES + 4}"

    def test_kinds_preserved(self):
        board = {}
        for kind in ("fact", "decision", "discovery", "artifact_ref", "open_question"):
            append_scratchpad_entry(board, kind, f"{kind} content")
        assert [e["kind"] for e in board["entries"]] == [
            "fact", "decision", "discovery", "artifact_ref", "open_question",
        ]


class TestScratchpadDigest:
    """Digest must be prompt-safe: compact, kind-tagged, never raising."""

    def test_empty_board_returns_empty_string(self):
        assert scratchpad_digest({}) == ""
        assert scratchpad_digest(None) == ""

    def test_entries_formatted_with_kinds(self):
        board = {"entries": [
            {"kind": "fact", "content": "repo uses bun"},
            {"kind": "decision", "content": "switched to bun install"},
        ]}
        digest = scratchpad_digest(board)
        assert "WORKING MEMORY" in digest
        assert "- [fact] repo uses bun" in digest
        assert "- [decision] switched to bun install" in digest

    def test_malformed_entries_never_raise(self):
        digest = scratchpad_digest({"entries": ["junk", {"no_kind": 1}, 42]})
        assert "junk" in digest
        assert "42" in digest

    def test_missing_entries_key(self):
        assert scratchpad_digest({"other": 1}) == ""


class TestAgentTaskScratchpadField:
    """Model default + persistence round-trip."""

    def _task(self, with_entries: bool) -> AgentTask:
        task = AgentTask(conversation_id="c", user_id="u", goal="Build a dashboard")
        if with_entries:
            append_scratchpad_entry(task.scratchpad, "fact", "repo uses bun", step_index=1)
        return task

    def test_default_empty_dict(self):
        task = AgentTask(conversation_id="c", user_id="u", goal="g")
        assert task.scratchpad == {}

    def test_round_trip_model_dump(self):
        task = self._task(with_entries=True)
        dumped = task.model_dump()
        assert dumped["scratchpad"]["entries"][0]["content"] == "repo uses bun"
        restored = AgentTask(**{**dumped, "id": task.id})
        assert restored.scratchpad == task.scratchpad


class TestCompressorInjection:
    """Digest appears in step + synthesis payloads only when non-empty."""

    def _task(self, with_entries: bool) -> AgentTask:
        task = AgentTask(conversation_id="c", user_id="u", goal="Build a dashboard")
        if with_entries:
            append_scratchpad_entry(task.scratchpad, "fact", "repo uses bun", step_index=1)
        return task

    def test_step_payload_includes_digest(self):
        payload = AgentContextCompressor.build_step_payload(self._task(True), 2)
        assert "WORKING MEMORY" in payload
        assert "repo uses bun" in payload
        assert "do not contradict or rediscover" in payload

    def test_step_payload_empty_board_has_no_section(self):
        payload = AgentContextCompressor.build_step_payload(self._task(False), 1)
        assert "WORKING MEMORY" not in payload

    def test_synthesis_payload_includes_digest(self):
        payload = AgentContextCompressor.build_synthesis_payload(self._task(True))
        assert "WORKING MEMORY" in payload
        assert "repo uses bun" in payload


class TestManagerWiring:
    """Structural contract: the manager writes notes and persists the board."""

    def _source(self) -> str:
        with open(_TASK_MANAGER_PATH, "r", encoding="utf-8") as f:
            return f.read()

    def test_save_state_persists_scratchpad(self):
        assert '"scratchpad": self.task.scratchpad' in self._source()

    def test_write_note_helper_exists_and_delegates(self):
        tree = ast.parse(self._source())
        methods = [
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_write_note"
        ]
        assert methods, "AgentTaskManager._write_note is required"
        assert "append_scratchpad_entry(self.task.scratchpad" in self._source()

    def test_all_capture_sites_wired(self):
        src = self._source()
        for kind in ('"fact"', '"decision"', '"discovery"', '"artifact_ref"'):
            assert f"self._write_note(\n                        {kind}," in src or kind in src, \
                f"capture site for {kind} missing"
        assert src.count("self._write_note(") >= 6

