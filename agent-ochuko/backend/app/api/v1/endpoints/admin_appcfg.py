# app/api/v1/endpoints/admin_appcfg.py
"""
Admin endpoint: write live config values to Azure App Configuration.

All keys are written with label 'production' so they are picked up
by the existing load_config() reader.

The in-memory _CONFIG_CACHE is updated immediately after a successful write
so changes take effect on this instance without a restart.
"""
import os
import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from azure.appconfiguration import AzureAppConfigurationClient, ConfigurationSetting

from app.api.v1.endpoints.admin import require_admin
from app.services.admin_service import write_audit_log
from app.core import config as app_config  # to update _CONFIG_CACHE

logger = logging.getLogger("app.api.v1.endpoints.admin_appcfg")
router = APIRouter()

# Keys that admins are allowed to write via this endpoint.
# Explicit allowlist — never allow arbitrary key writes.
WRITABLE_KEYS = {
    "THINK_MODEL_DEPLOYMENT",
    "SOLVE_MODEL_DEPLOYMENT",
    "NANO_MODEL_DEPLOYMENT",
    "COMPACTION_MODEL_DEPLOYMENT",
    "HUGGINGFACE_IMAGE_MODEL",
    "NANO_MAX_TURNS",
    "COMPACTION_THRESHOLD",
    "REGISTRATION_LIMIT",
    "MAINTENANCE_MODE",
    "GLOBAL_DAILY_TOKEN_BUDGET",
    "THINK_PROMPT",
    "SOLVE_PROMPT",
    "DISCUSS_PROMPT",
    "NANO_PROMPT",
}


class AppCfgUpdateRequest(BaseModel):
    updates: Dict[str, str] = Field(
        ...,
        description=(
            "Key/value pairs to write to Azure App Configuration "
            "(label=production). Only allow-listed keys are accepted."
        ),
    )


@router.patch("/settings/appcfg", summary="Write live config values to Azure App Configuration")
async def update_app_config(
    body: AppCfgUpdateRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Write one or more config values to Azure App Configuration.

    - Only keys in the WRITABLE_KEYS allowlist are accepted.
    - Values are written with label='production'.
    - The in-memory cache is updated immediately.
    - Every successful write is recorded in the audit log.
    """
    connection_string = os.getenv("AZURE_APP_CONFIG_CONNECTION_STRING")
    if not connection_string:
        raise HTTPException(
            status_code=500,
            detail="AZURE_APP_CONFIG_CONNECTION_STRING is not configured on this server.",
        )

    # Validate keys before touching Azure
    unknown_keys = set(body.updates.keys()) - WRITABLE_KEYS
    if unknown_keys:
        raise HTTPException(
            status_code=422,
            detail=f"Keys not in allowlist: {sorted(unknown_keys)}. "
                   f"Permitted keys: {sorted(WRITABLE_KEYS)}",
        )

    written = []
    try:
        client = AzureAppConfigurationClient.from_connection_string(connection_string)
        for key, value in body.updates.items():
            setting = ConfigurationSetting(key=key, value=value, label="production")
            client.set_configuration_setting(setting)

            # Update in-memory cache immediately — no restart required
            app_config._CONFIG_CACHE[key] = value
            written.append(key)
            logger.info("AppConfig key '%s' updated by admin %s", key, admin["sub"])

    except Exception as exc:
        logger.error("Failed to write to Azure App Configuration: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"Azure App Configuration write failed: {exc}",
        )

    write_audit_log(
        admin_id=admin["sub"],
        action="update_appcfg",
        resource_type="azure_app_configuration",
        metadata={"keys_written": written},
    )

    return {"status": "written", "keys": written}
