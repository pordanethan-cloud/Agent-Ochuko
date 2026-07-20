"""
Scope Contracts & Task Boundary Module for Agent Ochuko.
Enforces strict filesystem path restrictions ensuring code execution and file edits
cannot escape authorized sandbox workspace boundaries.
"""
import os
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class ScopeContractViolation(Exception):
    """Raised when an operation attempts to access paths outside the scope contract."""
    pass


class ScopeContract:
    """Enforces task boundaries and path containment."""

    @staticmethod
    def validate_sandbox_path(target_path: str, conversation_id: str) -> Tuple[bool, Optional[str]]:
        """
        Ensures target_path resolves cleanly inside /tmp/sandbox_{conversation_id}/ or subfolders.
        Prevents directory traversal attacks (e.g. ../../etc/passwd).
        """
        try:
            # Expected root
            base_dir = os.path.abspath(os.path.join("/tmp", f"sandbox_{conversation_id}")).replace("\\", "/")
            resolved_target = os.path.abspath(target_path).replace("\\", "/")

            if not resolved_target.startswith(base_dir):
                reason = f"Path '{target_path}' violates scope contract (outside allowed sandbox root: {base_dir})"
                logger.error(f"ScopeContract violation: {reason}")
                return False, reason

            return True, None
        except Exception as e:
            return False, f"Path resolution error: {str(e)}"

    @staticmethod
    def enforce_sandbox_path(target_path: str, conversation_id: str):
        """Enforces path containment or raises ScopeContractViolation."""
        valid, reason = ScopeContract.validate_sandbox_path(target_path, conversation_id)
        if not valid:
            raise ScopeContractViolation(reason)


scope_contract = ScopeContract()
