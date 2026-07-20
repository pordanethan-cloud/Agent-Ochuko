"""
Verification Gates Module for Agent Ochuko.
Performs programmatic output verification after tool executions, sandbox runs, and document edits.
Checks AST syntax, linting, file structure integrity, and output format schemas.
"""
import ast
import json
import logging
import os
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


class VerificationGateError(Exception):
    """Raised when an output fails verification gates."""
    pass


class VerificationGates:
    """Core verification gate pipeline."""

    @staticmethod
    def verify_python_syntax(code: str) -> Tuple[bool, Optional[str]]:
        """Verify Python code syntax via AST parsing."""
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            error_msg = f"Syntax error at line {e.lineno}, col {e.offset}: {e.msg}"
            logger.warning(f"Python verification gate failed: {error_msg}")
            return False, error_msg
        except Exception as e:
            return False, f"AST parse error: {str(e)}"

    @staticmethod
    def verify_document_header(file_path: str) -> Tuple[bool, Optional[str]]:
        """Verify binary document zip/PDF magic byte headers."""
        if not os.path.exists(file_path):
            return False, f"File does not exist: {file_path}"

        ext = os.path.splitext(file_path.lower())[1]
        try:
            with open(file_path, "rb") as f:
                header = f.read(8)

            if ext in [".docx", ".xlsx", ".pptx"]:
                # ZIP header check (PK\x03\x04)
                if not header.startswith(b"PK\x03\x04"):
                    return False, f"Invalid Office document header for {ext} file."
            elif ext == ".pdf":
                # PDF header check (%PDF-)
                if not header.startswith(b"%PDF"):
                    return False, "Invalid PDF document header magic bytes."

            return True, None
        except Exception as e:
            return False, f"Header check error: {str(e)}"

    @staticmethod
    def verify_json_schema(payload_str: str, required_keys: List[str]) -> Tuple[bool, Optional[str]]:
        """Verify JSON payload formatting and required schema keys."""
        try:
            data = json.loads(payload_str)
            if not isinstance(data, dict):
                return False, "Output payload is not a JSON object."
            
            missing = [k for k in required_keys if k not in data]
            if missing:
                return False, f"Missing required keys in payload: {missing}"
            
            return True, None
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON string: {e.msg}"


# Global instance
verification_gates = VerificationGates()
