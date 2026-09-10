"""Smoke test: the full app must import cleanly.

Catches runtime NameErrors / broken import chains (e.g. a module referencing
a symbol it never imported) that py_compile cannot detect.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_app_imports_cleanly():
    from app.main import app  # noqa: F401


def test_agent_planner_imports_cleanly():
    from app.core.agent_planner import _PLANNER_SYSTEM  # noqa: F401
    assert "OODA" in _PLANNER_SYSTEM
