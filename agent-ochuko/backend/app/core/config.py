# app/core/config.py
import os
import logging
from typing import Dict, Optional
from dotenv import load_dotenv
from azure.appconfiguration import AzureAppConfigurationClient

# Load local environment variables from .env first
load_dotenv()

logger = logging.getLogger("app.core.config")
logging.basicConfig(level=logging.INFO)

# Global in-memory configuration cache
_CONFIG_CACHE: Dict[str, str] = {}


def load_config() -> None:
    """
    Loads configuration settings from Azure App Configuration at startup
    and caches them in-memory. Sensitive secrets are loaded from the environment
    (local .env in development, or Key Vault in production).
    """
    global _CONFIG_CACHE
    
    # 1. Start with environment variables as baseline config
    for key, value in os.environ.items():
        _CONFIG_CACHE[key] = value

    # 2. Layer Azure App Configuration on top
    connection_string = os.getenv("AZURE_APP_CONFIG_CONNECTION_STRING")
    if not connection_string:
        logger.warning(
            "AZURE_APP_CONFIG_CONNECTION_STRING not set. Using local env baseline only."
        )
        return

    try:
        logger.info("Connecting to Azure App Configuration...")
        client = AzureAppConfigurationClient.from_connection_string(connection_string)
        
        # Fetch all configurations with label 'production'
        fetched_items = client.list_configuration_settings(label_filter="production")
        count = 0
        for item in fetched_items:
            # Overwrite environment baseline with App Config values
            _CONFIG_CACHE[item.key] = item.value
            os.environ[item.key] = item.value
            count += 1
            
        logger.info(f"Loaded {count} configurations from Azure App Configuration.")
    except Exception as e:
        logger.error(f"Failed to load configurations from Azure App Configuration: {e}")
        # In case of failure, we still have the environment variables baseline


async def get_config(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Retrieves a configuration value from the cached settings.
    If the key is not present, falls back to the default value.
    """
    return _CONFIG_CACHE.get(key, default)


import asyncio

_polling_task: Optional[asyncio.Task] = None


async def poll_config_loop(interval_seconds: int = 300) -> None:
    """
    Asynchronous loop that periodically reloads configurations from Azure App Configuration.
    """
    logger.info(f"Starting background config polling loop (every {interval_seconds}s)...")
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, load_config)
            logger.debug("Background config reload completed.")
    except asyncio.CancelledError:
        logger.info("Background config polling loop cancelled.")
    except Exception as e:
        logger.error(f"Error in background config polling loop: {e}")


def start_config_polling(interval_seconds: int = 300) -> None:
    """
    Start the background polling task.
    """
    global _polling_task
    if _polling_task is None:
        _polling_task = asyncio.create_task(poll_config_loop(interval_seconds))


def stop_config_polling() -> None:
    """
    Stop the background polling task.
    """
    global _polling_task
    if _polling_task is not None:
        _polling_task.cancel()
        _polling_task = None

