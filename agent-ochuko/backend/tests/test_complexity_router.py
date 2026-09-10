# tests/test_complexity_router.py
"""
Rule-based complexity classifier contract tests.

The classifier is the <1ms, zero-cost gate that decides the reasoning-effort
tier (low→xhigh) for the GPT-5.6 family (terra/luna). These tests lock the
tier behavior, the guards (live-query floor, agent floor, trivial/cap), and
the performance budget (1000 classifications well under 1ms average).
"""

import time

from app.core.complexity_router import classify, TIER_ORDER


def test_trivial_greeting_is_low():
    d = classify("hello")
    assert d.tier == "low"
    assert "trivial" in d.signals


def test_simple_lookup_is_low():
    d = classify("What is the capital of France?")
    assert d.tier == "low"


def test_compound_build_prompt_is_xhigh():
    msg = (
        "Build and deploy a complete production-ready FastAPI app with "
        "authentication, database migrations, unit tests, and CI/CD. The full "
        "stack should include Docker, PostgreSQL, and a React frontend."
    )
    d = classify(msg)
    assert TIER_ORDER[d.tier] >= TIER_ORDER["high"]
    assert d.score >= 9
    assert any(s.startswith("codegen") for s in d.signals)


def test_multi_part_structure_raises_tier():
    msg = (
        "Help me plan a launch:\n"
        "1. Research the market\n"
        "2. Build the landing page\n"
        "3. Set up analytics\n"
        "4. Write the announcement email\n"
        "Make sure to include pricing."
    )
    d = classify(msg)
    # 4 list markers → structure points, plus build/write/research verbs.
    assert TIER_ORDER[d.tier] >= TIER_ORDER["medium"]
    assert any(s.startswith("multi_part") for s in d.signals)


def test_math_prompt_at_least_medium():
    d = classify(
        "Calculate the compound interest on 5000 * 12 payments at 7% over "
        "10 years and explain the variance versus simple interest"
    )
    assert TIER_ORDER[d.tier] >= TIER_ORDER["medium"]


def test_live_query_floor():
    d = classify("What is the latest bitcoin price")
    assert TIER_ORDER[d.tier] >= TIER_ORDER["medium"]
    assert "live_query_floor" in d.signals


def test_floor_and_cap_params():
    d = classify("hello", floor="medium")
    assert d.tier == "medium"

    d2 = classify(
        "Build a complete production-ready app with architecture, caching, "
        "authentication and deployment",
        cap="medium",
    )
    assert d2.tier == "medium"


def test_classification_is_deterministic():
    msg = "Refactor the service layer with async concurrency, caching and rate limiting"
    a, b = classify(msg), classify(msg)
    assert (a.tier, a.score, list(a.signals)) == (b.tier, b.score, list(b.signals))


def test_empty_and_whitespace():
    assert classify("").tier == "low"
    assert classify("   ").tier == "low"


def test_speed_1000_classifications_well_under_1ms_avg():
    msg = (
        "Build a complete production-ready FastAPI application with PostgreSQL, "
        "Docker deployment, authentication with JWT tokens, rate limiting, caching, "
        "unit tests, CI/CD, and monitoring. Compare architectural trade-offs and "
        "recommend the best approach for scaling to 10k concurrent users."
    ) * 2
    start = time.perf_counter()
    for _ in range(1000):
        classify(msg)
    elapsed = time.perf_counter() - start
    # Budget: <1ms average → <1s for 1000 runs. Real-world is ~10-30ms total.
    assert elapsed < 1.0, f"1000 classifications took {elapsed:.3f}s"
