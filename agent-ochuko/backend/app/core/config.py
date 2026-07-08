# app/core/config.py
import os
import logging
import json
from typing import Dict, Optional
from dotenv import load_dotenv
from azure.appconfiguration import AzureAppConfigurationClient
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential

# Load local environment variables from .env first
load_dotenv()

logger = logging.getLogger("app.core.config")
logging.basicConfig(level=logging.INFO)

# Global in-memory configuration cache
_CONFIG_CACHE: Dict[str, str] = {}

_kv_clients: Dict[str, SecretClient] = {}

def _resolve_keyvault_ref(uri: str) -> Optional[str]:
    """
    Resolves an Azure Key Vault secret URI (e.g. https://<vault-name>.vault.azure.net/secrets/<secret-name>)
    using DefaultAzureCredential.
    """
    try:
        if not uri.startswith("https://"):
            return None
        parts = uri.split("/")
        if len(parts) < 5 or parts[3] != "secrets":
            return None
        vault_url = f"https://{parts[2]}"
        secret_name = parts[4]
        if vault_url not in _kv_clients:
            credential = DefaultAzureCredential()
            _kv_clients[vault_url] = SecretClient(vault_url=vault_url, credential=credential)
        client = _kv_clients[vault_url]
        secret = client.get_secret(secret_name)
        return secret.value
    except Exception as e:
        logger.error(f"Failed to resolve Key Vault reference URI {uri}: {e}")
        return None


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
            # Check if it is a Key Vault reference
            is_kv_ref = False
            uri = None
            if item.content_type and "keyvaultref" in item.content_type:
                is_kv_ref = True
            elif item.value and item.value.strip().startswith('{"uri":'):
                is_kv_ref = True

            if is_kv_ref:
                try:
                    ref_data = json.loads(item.value)
                    uri = ref_data.get("uri")
                except Exception:
                    pass
                
                # Check if it's already set in environment (in container apps, ACA injects them)
                env_val = os.environ.get(item.key)
                if env_val:
                    _CONFIG_CACHE[item.key] = env_val
                    logger.info(f"Using pre-set env value for Key Vault key: {item.key}")
                elif uri:
                    resolved_val = _resolve_keyvault_ref(uri)
                    if resolved_val:
                        _CONFIG_CACHE[item.key] = resolved_val
                        os.environ[item.key] = resolved_val
                        logger.info(f"Successfully resolved Key Vault reference for key: {item.key}")
                        count += 1
                    else:
                        logger.warning(f"Could not resolve Key Vault reference for key: {item.key}")
            else:
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

