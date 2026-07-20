"""
Circuit Breaker & Action Budget Module for Agent Ochuko.
Enforces per-request step limits, token spend caps, tool error loop detection, and runtime circuit breaking.
"""
import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ActionBudgetExceeded(Exception):
    """Raised when an agent turn exceeds action budget or step caps."""
    pass


class CircuitBreakerOpen(Exception):
    """Raised when repetitive tool failures open the circuit breaker."""
    pass


class CircuitBreaker:
    """Action budget tracker and circuit breaker for agent turn loops."""

    def __init__(self, max_steps: int = 10, max_consecutive_errors: int = 3):
        self.max_steps = max_steps
        self.max_consecutive_errors = max_consecutive_errors
        self.reset()

    def reset(self):
        """Reset budget counters for a new user turn."""
        self.current_step = 0
        self.consecutive_errors = 0
        self.last_error_signature: Optional[str] = None
        self.start_time = time.time()

    def record_step(self, step_label: str = ""):
        """Increment step counter and check budget cap."""
        self.current_step += 1
        logger.info(f"Agent Action Budget Step {self.current_step}/{self.max_steps}: {step_label}")
        if self.current_step > self.max_steps:
            raise ActionBudgetExceeded(
                f"Agent step limit exceeded ({self.current_step}/{self.max_steps}). "
                "Halting turn loop to protect resources."
            )

    def record_error(self, error_signature: str):
        """Record tool failure signature and check circuit breaker threshold."""
        if error_signature == self.last_error_signature:
            self.consecutive_errors += 1
        else:
            self.consecutive_errors = 1
            self.last_error_signature = error_signature

        logger.warning(
            f"Circuit breaker error signature '{error_signature}' count: {self.consecutive_errors}/{self.max_consecutive_errors}"
        )

        if self.consecutive_errors >= self.max_consecutive_errors:
            raise CircuitBreakerOpen(
                f"Circuit breaker tripped! Repeated error signature '{error_signature}' "
                f"occurred {self.consecutive_errors} times consecutively."
            )

    def record_success(self):
        """Reset consecutive error count on successful tool execution."""
        self.consecutive_errors = 0
        self.last_error_signature = None


# Global CircuitBreaker Factory
def create_turn_circuit_breaker(max_steps: int = 10) -> CircuitBreaker:
    return CircuitBreaker(max_steps=max_steps)
