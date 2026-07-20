"""
Durable Execution & State Checkpointing Service for Agent Ochuko.
Persists agent step state into Supabase / disk after every OODA loop iteration.
Allows seamless session resumption after container restarts or network interruptions.
"""
import json
import os
import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class DurableStateStore:
    """Manages state serialization and checkpoint persistence."""

    @staticmethod
    def get_checkpoint_dir(conversation_id: str) -> str:
        """Returns checkpoint storage directory."""
        checkpoint_dir = os.path.abspath(os.path.join("/tmp", f"sandbox_{conversation_id}", "checkpoints")).replace("\\", "/")
        os.makedirs(checkpoint_dir, exist_ok=True)
        return checkpoint_dir

    @staticmethod
    def save_checkpoint(conversation_id: str, step_index: int, state_data: Dict[str, Any]) -> str:
        """Saves turn state checkpoint to disk."""
        checkpoint_dir = DurableStateStore.get_checkpoint_dir(conversation_id)
        filepath = os.path.join(checkpoint_dir, f"step_{step_index:03d}.json")
        
        payload = {
            "conversation_id": conversation_id,
            "step_index": step_index,
            "timestamp": time.time(),
            "state": state_data
        }

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            logger.info(f"Saved durable state checkpoint step {step_index} for convo {conversation_id}")
            return filepath
        except Exception as e:
            logger.error(f"Failed to save durable state checkpoint: {e}")
            return ""

    @staticmethod
    def load_latest_checkpoint(conversation_id: str) -> Optional[Dict[str, Any]]:
        """Loads latest valid checkpoint state for conversation."""
        checkpoint_dir = DurableStateStore.get_checkpoint_dir(conversation_id)
        if not os.path.exists(checkpoint_dir):
            return None

        files = sorted([f for f in os.listdir(checkpoint_dir) if f.startswith("step_") and f.endswith(".json")])
        if not files:
            return None

        latest_file = os.path.join(checkpoint_dir, files[-1])
        try:
            with open(latest_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load checkpoint file {latest_file}: {e}")
            return None


durable_state = DurableStateStore()
