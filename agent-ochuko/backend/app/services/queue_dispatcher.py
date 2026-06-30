# app/services/queue_dispatcher.py
"""
Azure Queue Storage dispatcher.
Handles serialising and enqueuing background agent jobs (Pattern B)
to the storage queue where they are picked up by Azure Function triggers.
"""
import os
import json
import base64
import logging
from azure.storage.queue import QueueClient

logger = logging.getLogger("app.services.queue_dispatcher")


def enqueue_job(job_id: str, job_type: str, input_metadata: dict, user_id: str) -> None:
    """
    Enqueues a job payload to the Azure Storage Queue 'agent-jobs'.
    Base64 encodes the message payload to ensure compatibility with Azure Functions QueueTrigger.
    """
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not conn_str:
        raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING must be set in the environment.")

    queue_name = os.getenv("AZURE_QUEUE_NAME", "agent-jobs")

    try:
        # Initialise QueueClient using the unified storage connection string
        queue_client = QueueClient.from_connection_string(conn_str, queue_name)

        payload = {
            "job_id": job_id,
            "type": job_type,
            "input_metadata": input_metadata,
            "user_id": user_id
        }

        # Serialise to JSON bytes and base64-encode
        message_json = json.dumps(payload)
        message_bytes = message_json.encode("utf-8")
        message_b64 = base64.b64encode(message_bytes).decode("utf-8")

        logger.info(f"Enqueuing job {job_id} of type {job_type} to queue {queue_name}...")
        queue_client.send_message(message_b64)
        logger.info(f"Job {job_id} enqueued successfully.")

    except Exception as e:
        logger.error(f"Failed to enqueue job {job_id}: {e}")
        raise RuntimeError(f"Failed to dispatch job to queue: {e}")
