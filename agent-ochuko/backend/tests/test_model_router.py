import pytest
from app.core import model_router
from app.core.config import _CONFIG_CACHE
from app.core.skills import BASE_IDENTITY, SKILLS, get_skill_prompt


@pytest.mark.asyncio
async def test_route_discuss():
    # DISCUSS mode should always route to nano deployment and use discuss prompt
    _CONFIG_CACHE["NANO_MODEL_DEPLOYMENT"] = "gpt-nano-test"
    _CONFIG_CACHE["DISCUSS_PROMPT"] = "discuss-test-prompt"

    decision = await model_router.route(
        user_message="How do we build a startup?",
        mode="discuss",
        conversation_id="test-conv-id",
        nano_turn_count=0
    )

    assert decision.routing_mode == "discuss"
    assert decision.deployment == "gpt-nano-test"
    assert "You are Agent Ochuko" in decision.system_prompt
    assert decision.was_intercepted is False


@pytest.mark.asyncio
async def test_route_nano_interception():
    # Trivial message in THINK mode should trigger Nano interception if turn count is below max
    _CONFIG_CACHE["NANO_MODEL_DEPLOYMENT"] = "gpt-nano-test"
    _CONFIG_CACHE["NANO_PROMPT"] = "nano-test-prompt"
    _CONFIG_CACHE["NANO_MAX_TURNS"] = "3"

    decision = await model_router.route(
        user_message="hello",
        mode="think",
        conversation_id="test-conv-id",
        nano_turn_count=1
    )

    assert decision.routing_mode == "nano"
    assert decision.deployment == "gpt-nano-test"
    assert decision.system_prompt == "nano-test-prompt"
    assert decision.was_intercepted is True


@pytest.mark.asyncio
async def test_route_nano_interception_max_turns():
    # Trivial message in THINK mode should bypass Nano interception if turn count reaches max
    _CONFIG_CACHE["THINK_MODEL_DEPLOYMENT"] = "gpt-think-test"
    _CONFIG_CACHE["THINK_PROMPT"] = "think-test-prompt"
    _CONFIG_CACHE["NANO_MAX_TURNS"] = "3"

    decision = await model_router.route(
        user_message="hello",
        mode="think",
        conversation_id="test-conv-id",
        nano_turn_count=3
    )

    assert decision.routing_mode == "think"
    assert decision.deployment == "gpt-think-test"
    assert "You are Agent Ochuko" in decision.system_prompt
    assert decision.was_intercepted is False


@pytest.mark.asyncio
async def test_route_non_trivial_message():
    # Detailed message should route directly to THINK/SOLVE and not be intercepted
    _CONFIG_CACHE["THINK_MODEL_DEPLOYMENT"] = "gpt-think-test"
    _CONFIG_CACHE["THINK_PROMPT"] = "think-test-prompt"
    _CONFIG_CACHE["NANO_MAX_TURNS"] = "3"

    decision = await model_router.route(
        user_message="Explain quantum computing in detail.",
        mode="think",
        conversation_id="test-conv-id",
        nano_turn_count=0
    )

    assert decision.routing_mode == "think"
    assert decision.deployment == "gpt-think-test"
    assert "You are Agent Ochuko" in decision.system_prompt
    assert decision.was_intercepted is False


# ── Fable-5 distillation contract tests ───────────────────────────────────────

def test_base_identity_token_cap():
    # BASE_IDENTITY must stay within the 500-token budget (word-count proxy:
    # tokens ~= words * 1.3 for prose). Guards against prompt bloat regressions.
    estimated_tokens = int(len(BASE_IDENTITY.split()) * 1.3)
    assert estimated_tokens <= 500, (
        f"BASE_IDENTITY bloat: ~{estimated_tokens} estimated tokens "
        f"({len(BASE_IDENTITY.split())} words). Trim the prompt."
    )


def test_conduct_block_present():
    # Distilled Fable-5 conduct contracts must survive in BASE_IDENTITY.
    lower = BASE_IDENTITY.lower()
    assert "mistake" in lower or "corrected" in lower
    assert "wellbeing" in lower
    assert "no emojis" in lower


def test_research_skill_citation_contract():
    # Research-class prompts must receive the citation contract and the
    # fetch_url tool reference.
    prompt = get_skill_prompt("compare iPhone vs Samsung latest prices 2026")
    assert "[1](" in prompt or "[n](url)" in prompt
    assert "**Sources:**" in prompt or "Sources:" in prompt
    assert "fetch_url" in prompt


def test_live_data_queries_bypass_nano():
    # Live/current-data lookups must NOT be intercepted to nano — they need
    # the full model's search tool capabilities.
    assert model_router._is_simple_request("who is the latest CBN governor") is False
    assert model_router._is_simple_request("what is the current price of bitcoin") is False
    # Static facts may still be intercepted for cost efficiency.
    assert model_router._is_simple_request("who is Albert Einstein") is True


def test_fetch_url_html_to_text():
    from app.api.v1.endpoints.chat import _html_to_text

    html = (
        "<html><head><style>body { color: red; }</style></head>"
        "<body><script>alert('x')</script>"
        "<h1>Title Here</h1>"
        "<p>First   paragraph with   spaces.</p>"
        "<p>Second paragraph.</p>"
        "</body></html>"
    )
    text = _html_to_text(html)
    assert "Title Here" in text
    assert "First paragraph with spaces." in text
    assert "Second paragraph." in text
    assert "alert" not in text
    assert "color: red" not in text


@pytest.mark.asyncio
async def test_fetch_url_bad_url_degrades_gracefully():
    # Invalid URLs must return a graceful error string, never raise into the
    # model context.
    from app.api.v1.endpoints.chat import _perform_fetch_url

    result = await _perform_fetch_url("not-a-url")
    assert result.startswith("fetch_url error")
    result2 = await _perform_fetch_url("")
    assert result2.startswith("fetch_url error")


def test_time_aware_query_appends_year():
    from app.api.v1.endpoints.chat import _time_aware_query
    from datetime import datetime

    year = str(datetime.now().year)
    assert _time_aware_query("latest Nigeria tax reform").endswith(year)
    # Static queries stay untouched; explicit years are not duplicated.
    assert _time_aware_query("capital of France") == "capital of France"
    assert _time_aware_query(f"tax reform {year} summary") == f"tax reform {year} summary"


def test_relative_dates_resolved_in_query():
    # "yesterday's games" must become an explicit calendar-date query so
    # search engines surface exactly the right day's results (regression:
    # "yesterday night game" used to reach the engine unresolved).
    from datetime import datetime, timedelta, timezone

    from app.api.v1.endpoints.chat import _time_aware_query, _resolve_relative_dates

    wat = timezone(timedelta(hours=1))
    yesterday = (datetime.now(wat) - timedelta(days=1)).strftime("%B %d, %Y")
    today = datetime.now(wat).strftime("%B %d, %Y")

    assert yesterday in _time_aware_query("champions league games last night")
    assert yesterday in _time_aware_query("yesterday's football results")
    assert today in _time_aware_query("who won the game this morning")
    # Non-relative queries pass through untouched.
    assert _resolve_relative_dates("capital of France") == "capital of France"


# ── GPT-5.6 family + complexity routing tests ────────────────────────────────

@pytest.mark.asyncio
async def test_default_deployments_are_gpt56_family():
    # Clear cached deployments so router defaults apply.
    _CONFIG_CACHE.pop("THINK_MODEL_DEPLOYMENT", None)
    _CONFIG_CACHE.pop("SOLVE_MODEL_DEPLOYMENT", None)
    _CONFIG_CACHE.pop("NANO_MODEL_DEPLOYMENT", None)

    think = await model_router.route("Explain quantum computing in detail.", "think", "c1", 0)
    solve = await model_router.route("Explain quantum computing in detail.", "solve", "c1", 0)
    discuss = await model_router.route("hello", "discuss", "c1", 0)

    assert think.deployment == "gpt-5.6-terra"
    assert solve.deployment == "gpt-5.6-luna"
    assert discuss.deployment == "gpt-5.6-luna"


@pytest.mark.asyncio
async def test_routing_decision_carries_complexity_and_effort():
    _CONFIG_CACHE["THINK_MODEL_DEPLOYMENT"] = "gpt-5.6-terra"
    _CONFIG_CACHE["NANO_MAX_TURNS"] = "3"

    decision = await model_router.route(
        "Build and deploy a complete production-ready FastAPI app with authentication, "
        "database migrations, unit tests, and CI/CD.",
        "think", "c1", 0,
    )
    assert decision.complexity in ("high", "xhigh")
    assert decision.reasoning_effort in ("high", "xhigh")
    assert "complexity=" in decision.routing_reason


@pytest.mark.asyncio
async def test_nano_and_discuss_effort_none():
    _CONFIG_CACHE["NANO_MODEL_DEPLOYMENT"] = "gpt-5.6-luna"
    _CONFIG_CACHE["NANO_MAX_TURNS"] = "3"

    d1 = await model_router.route("hello", "think", "c1", 1)  # intercepted
    assert d1.routing_mode == "nano"
    assert d1.reasoning_effort == "none"

    d2 = await model_router.route("hello", "discuss", "c1", 0)
    assert d2.reasoning_effort == "none"


@pytest.mark.asyncio
async def test_terra_effort_map_override():
    _CONFIG_CACHE["THINK_MODEL_DEPLOYMENT"] = "gpt-5.6-terra"
    _CONFIG_CACHE["TERRA_EFFORT_MAP"] = (
        '{"low":"low","medium":"low","high":"medium","xhigh":"medium"}'
    )
    _CONFIG_CACHE["NANO_MAX_TURNS"] = "3"

    decision = await model_router.route(
        "Build and deploy a complete production-ready FastAPI app with authentication, "
        "database migrations, unit tests, and CI/CD.",
        "think", "c1", 0,
    )
    assert decision.complexity in ("high", "xhigh")
    assert decision.reasoning_effort == "medium"

    _CONFIG_CACHE.pop("TERRA_EFFORT_MAP", None)


@pytest.mark.asyncio
async def test_agent_mode_effort_floor():
    _CONFIG_CACHE["THINK_MODEL_DEPLOYMENT"] = "gpt-5.6-terra"
    _CONFIG_CACHE["NANO_MAX_TURNS"] = "3"
    _CONFIG_CACHE.pop("TERRA_EFFORT_MAP", None)

    # Trivial message beyond nano max turns → think branch for agent requests.
    decision = await model_router.route("hello", "agent", "c1", 99)
    assert decision.routing_mode == "think"
    # Agent/Ultra never runs below medium complexity.
    assert decision.complexity == "medium"
    assert decision.reasoning_effort == "medium"


@pytest.mark.asyncio
async def test_is_reasoning_model_includes_gpt56_family():
    from app.core.agent_config import is_reasoning_model

    assert await is_reasoning_model("gpt-5.6-terra") is True
    assert await is_reasoning_model("gpt-5.6-luna") is True
    assert await is_reasoning_model("gpt-think-test") is False
