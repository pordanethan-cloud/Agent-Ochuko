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
  AGENT_STEP_TIMEOUT_SECS    Per-iteration timeout in seconds (default: 45)
"""

from app.core.config import get_config


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
        "discuss": ("MAX_AGENT_ITERS_DISCUSS", "1"),
        "nano":    ("MAX_AGENT_ITERS_DISCUSS", "1"),
    }

    key, default = mode_key_map.get(mode.lower(), ("MAX_AGENT_ITERATIONS", str(global_cap)))
    raw = await get_config(key, default)
    try:
        return max(1, int(raw))
    except (ValueError, TypeError):
        return global_cap


async def get_step_timeout() -> int:
    """Returns the per-iteration step timeout in seconds (default: 45)."""
    raw = await get_config("AGENT_STEP_TIMEOUT_SECS", "45")
    try:
        return max(10, int(raw))
    except (ValueError, TypeError):
        return 45
