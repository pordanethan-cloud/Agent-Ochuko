import pytest
from app.core import model_router
from app.core.config import _CONFIG_CACHE


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
