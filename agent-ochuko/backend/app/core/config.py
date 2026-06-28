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
