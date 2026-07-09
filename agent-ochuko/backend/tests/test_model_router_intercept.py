import pytest
from app.core import model_router
from app.core.config import _CONFIG_CACHE

@pytest.mark.asyncio
async def test_trivial_and_simple_regex_check():
    # Greetings & acknowledgements
    assert model_router._is_trivial("hello") is True
    assert model_router._is_trivial("thank you") is True
    assert model_router._is_trivial("ok") is True
    
    # Whitelisted simple informational lookups
    assert model_router._is_simple_request("football live scores") is True
    assert model_router._is_simple_request("weather in Lagos") is True
    assert model_router._is_simple_request("what is the time in London?") is True
    assert model_router._is_simple_request("who is the president of Nigeria") is True
    
    # Non-simple request (long or containing programming/plan indicators)
    assert model_router._is_simple_request("write a python script to calculate fibonacci") is False
    assert model_router._is_simple_request("create a pdf report of our monthly budget") is False
    assert model_router._is_simple_request(
        "what is the capital of France and explain its historical significance since 1789 with a structured outline and timeline"
    ) is False

@pytest.mark.asyncio
async def test_model_router_intercept_logic():
    # Seed configuration cache
    _CONFIG_CACHE["NANO_MODEL_DEPLOYMENT"] = "gpt-nano-test"
    _CONFIG_CACHE["THINK_MODEL_DEPLOYMENT"] = "gpt-think-test"
    _CONFIG_CACHE["SOLVE_MODEL_DEPLOYMENT"] = "gpt-solve-test"
    _CONFIG_CACHE["NANO_MAX_TURNS"] = "3"

    # Case 1: Simple query whitelisted in THINK mode -> gets intercepted to nano
    decision_1 = await model_router.route(
        user_message="football live scores",
        mode="think",
        nano_turn_count=0
    )
    assert decision_1.was_intercepted is True
    assert decision_1.routing_mode == "nano"
    assert decision_1.deployment == "gpt-nano-test"

    # Case 2: Simple query whitelisted in SOLVE mode -> gets intercepted to nano
    decision_2 = await model_router.route(
        user_message="weather in Lagos",
        mode="solve",
        nano_turn_count=0
    )
    assert decision_2.was_intercepted is True
    assert decision_2.routing_mode == "nano"
    assert decision_2.deployment == "gpt-nano-test"

    # Case 3: Real work in THINK mode -> NOT intercepted, goes to full think deployment
    decision_3 = await model_router.route(
        user_message="write a python script to calculate fibonacci",
        mode="think",
        nano_turn_count=0
    )
    assert decision_3.was_intercepted is False
    assert decision_3.routing_mode == "think"
    assert decision_3.deployment == "gpt-think-test"

    # Case 4: Long/complex question in THINK mode -> NOT intercepted
    decision_4 = await model_router.route(
        user_message="what is the capital of France and explain its historical significance since 1789 with a structured outline and timeline",
        mode="think",
        nano_turn_count=0
    )
    assert decision_4.was_intercepted is False
    assert decision_4.routing_mode == "think"
    assert decision_4.deployment == "gpt-think-test"
