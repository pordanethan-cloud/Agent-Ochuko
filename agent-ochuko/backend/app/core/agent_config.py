# app/core/agent_config.py
"""
Agent configuration — reads agentic loop settings from Azure App Configuration.

All values are read at call time from the in-memory cache (already kept fresh
by the config polling loop started in lifespan) so they can be tuned at runtime
without a redeploy.

Settings exposed:
  AGENT_LOOP_ENABLED         Feature flag — disables agentic loop globally if "false"
  MAX_AGENT_ITERATIONS       Hard cap on OODA loop iterations (default: 10)
  MAX_AGENT_ITERS_THINK      Per-mode cap for THINK mode (default: 10)
  MAX_AGENT_ITERS_SOLVE      Per-mode cap for SOLVE mode  (default: 6)
  MAX_AGENT_ITERS_DISCUSS    Per-mode cap for DISCUSS mode (default: 1)
  AGENT_STEP_TIMEOUT_SECS    Per-iteration timeout in seconds (default: 90)

Agent Mode Settings:
  AGENT_MODE_ENABLED         Feature flag for autonomous Agent Mode (default: true)
  AGENT_MODE_MAX_STEPS       Max plan steps per task (default: 12)
  AGENT_MODE_MAX_DURATION    Max wall-clock task runtime in seconds (default: 300 / 5 min)
  AGENT_MODE_STEP_TIMEOUT    Max timeout per step in seconds (default: 90)
  AGENT_MODE_AUTO_APPROVE    Risk threshold for auto-approval: 'low' | 'medium' | 'high' | 'none'
"""

from typing import Optional, Dict, Any
import json

from app.core.config import get_config


_REASONING_MODEL_PREFIXES = ("o1", "o3", "o4", "gpt-5.6")

# Mode → App Config key holding the JSON complexity→effort map.
# Terra (think/agent) and Luna (solve) share the same low→xhigh complexity
# scale; maps are runtime-tunable via App Config without redeploying.
_EFFORT_MAP_KEYS = {
    "think": "TERRA_EFFORT_MAP",
    "agent": "TERRA_EFFORT_MAP",
    "ultra": "TERRA_EFFORT_MAP",
    "solve": "LUNA_EFFORT_MAP",
}

_DEFAULT_EFFORT_MAP = {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh"}
_VALID_EFFORTS = ("none", "low", "medium", "high", "xhigh")


async def is_reasoning_model(deployment: Optional[str] = None) -> bool:
    """
    Returns True if *deployment* (or the current think deployment) is an
    o-series or GPT-5.6-family reasoning model that accepts
    reasoning_effort / max_completion_tokens parameters.
    """
    if deployment is None:
        deployment = await get_config("THINK_MODEL_DEPLOYMENT", "gpt-5.6-terra")
    name = (deployment or "").lower()
    return any(name.startswith(p) for p in _REASONING_MODEL_PREFIXES)


async def is_agent_loop_enabled() -> bool:
    """Returns True unless AGENT_LOOP_ENABLED is explicitly set to 'false'."""
    val = await get_config("AGENT_LOOP_ENABLED", "true")
    return val.lower() != "false"


async def get_max_iterations(mode: str = "think") -> int:
    """
    Returns the max OODA loop iterations for the given routing mode.
    Falls back to the global MAX_AGENT_ITERATIONS if mode-specific key not set.
    """
    global_cap_str = await get_config("MAX_AGENT_ITERATIONS", "10")
    try:
        global_cap = int(global_cap_str)
    except (ValueError, TypeError):
        global_cap = 10

    mode_key_map = {
        "think":   ("MAX_AGENT_ITERS_THINK",  str(global_cap)),
        "solve":   ("MAX_AGENT_ITERS_SOLVE",  "6"),
        "discuss": ("MAX_AGENT_ITERS_DISCUSS", "3"),
        "nano":    ("MAX_AGENT_ITERS_DISCUSS", "3"),
        "agent":   ("AGENT_MODE_MAX_STEPS",    "12"),
    }

    key, default = mode_key_map.get(mode.lower(), ("MAX_AGENT_ITERATIONS", str(global_cap)))
    raw = await get_config(key, default)
    try:
        return max(1, int(raw))
    except (ValueError, TypeError):
        return global_cap


async def get_step_timeout() -> int:
    """Returns the per-iteration step timeout in seconds (default: 90)."""
    raw = await get_config("AGENT_STEP_TIMEOUT_SECS", "90")
    try:
        return max(10, int(raw))
    except (ValueError, TypeError):
        return 90


async def get_agent_mode_config() -> Dict[str, Any]:
    """Returns runtime parameters for Agent Mode execution."""
    enabled_val = await get_config("AGENT_MODE_ENABLED", "true")
    max_steps_val = await get_config("AGENT_MODE_MAX_STEPS", "12")
    max_dur_val = await get_config("AGENT_MODE_MAX_DURATION", "300")
    step_to_val = await get_config("AGENT_MODE_STEP_TIMEOUT", "90")
    auto_app_val = await get_config("AGENT_MODE_AUTO_APPROVE", "medium")

    try:
        max_steps = int(max_steps_val)
    except (ValueError, TypeError):
        max_steps = 12

    try:
        max_duration = int(max_dur_val)
    except (ValueError, TypeError):
        max_duration = 300

    try:
        step_timeout = int(step_to_val)
    except (ValueError, TypeError):
        step_timeout = 90

    return {
        "enabled": enabled_val.lower() != "false",
        "max_steps": max_steps,
        "max_duration_seconds": max_duration,
        "step_timeout_seconds": step_timeout,
        "auto_approve_level": auto_app_val.lower() if auto_app_val else "medium",
    }


async def get_reasoning_effort(
    mode: str = "think",
    complexity: Optional[str] = None,
    deployment: Optional[str] = None,
) -> Optional[str]:
    """
    Returns the reasoning effort for the given mode + complexity tier.

    - nano/discuss routes to gpt-5.6-luna with effort "none" (cheapest).
    - think/agent/ultra resolve via TERRA_EFFORT_MAP; solve via LUNA_EFFORT_MAP.
      Maps are JSON objects: {"low": "...", "medium": "...", "high": "...", "xhigh": "..."}
      keyed by complexity tier, runtime-tunable via App Config.
    - complexity=None on a non-5.6 deployment preserves legacy o-series
      behavior (REASONING_EFFORT_THINK / REASONING_EFFORT_SOLVE).
    - Returns None when the deployment does not accept reasoning effort.
    """
    if not await is_reasoning_model(deployment):
        return None

    mode_lower = (mode or "think").lower()

    # Nano tier on the 5.6 family always runs at effort "none".
    if mode_lower in ("nano", "discuss"):
        return "none"

    # Legacy path for o-series deployments without complexity routing.
    if complexity is None and not (deployment or "").lower().startswith("gpt-5.6"):
        if mode_lower == "think":
            val = await get_config("REASONING_EFFORT_THINK", "high")
        elif mode_lower == "solve":
            val = await get_config("REASONING_EFFORT_SOLVE", "medium")
        else:
            return None
        return val.lower() if val and val.lower() in ("low", "medium", "high") else None

    map_key = _EFFORT_MAP_KEYS.get(mode_lower, "TERRA_EFFORT_MAP")
    raw = await get_config(map_key, json.dumps(_DEFAULT_EFFORT_MAP))
    try:
        effort_map = json.loads(raw)
        if not isinstance(effort_map, dict):
            effort_map = {}
    except (ValueError, TypeError):
        effort_map = {}

    tier = (complexity or "medium").lower()
    effort = effort_map.get(tier) or _DEFAULT_EFFORT_MAP.get(tier, "medium")
    return effort if effort in _VALID_EFFORTS else "medium"


async def get_max_completion_tokens(mode: str = "think", deployment: Optional[str] = None) -> Optional[int]:
    """
    Returns the maximum completion tokens limit for a given mode.
    Only applicable for o-series reasoning models — always returns None for GPT models.
    """
    if not await is_reasoning_model(deployment):
        return None
    if mode.lower() == "think":
        val = await get_config("MAX_COMPLETION_TOKENS_THINK", "16000")
    elif mode.lower() == "solve":
        val = await get_config("MAX_COMPLETION_TOKENS_SOLVE", "8000")
    else:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


# Mode → (App Config key, default output-token budget).
# Ultra (agent mode) and THINK get full Claude-grade headroom so generated
# files are never truncated; everything is runtime-tunable via App Config.
_OUTPUT_TOKEN_BUDGETS = {
    "ultra":   ("MAX_OUTPUT_TOKENS_ULTRA",   "32768"),
    "agent":   ("MAX_OUTPUT_TOKENS_ULTRA",   "32768"),
    "think":   ("MAX_OUTPUT_TOKENS_THINK",   "32768"),
    "solve":   ("MAX_OUTPUT_TOKENS_SOLVE",   "16384"),
    "discuss": ("MAX_OUTPUT_TOKENS_DISCUSS", "4096"),
    "nano":    ("MAX_OUTPUT_TOKENS_DISCUSS", "4096"),
}


async def get_max_output_tokens(mode: str = "think") -> int:
    """
    Returns the max_output_tokens budget for the given routing mode.
    Reads from App Configuration at call time (runtime-tunable).
    """
    key, default = _OUTPUT_TOKEN_BUDGETS.get(mode.lower(), ("MAX_OUTPUT_TOKENS_THINK", "32768"))
    raw = await get_config(key, default)
    try:
        return max(1024, int(raw))
    except (ValueError, TypeError):
        return int(default)
