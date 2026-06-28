import os
import json
import logging
from datetime import datetime, timezone, timedelta
import azure.functions as func
from supabase import create_client, Client
from azure.appconfiguration import AzureAppConfigurationClient
from openai import AzureOpenAI

# Initialize logging
logger = logging.getLogger("azure.functions.crons")

app = func.FunctionApp()

# ---------------------------------------------------------------------------
# Lazy Initializers for external clients
# ---------------------------------------------------------------------------

_supabase_client = None

def get_supabase() -> Client:
    """Lazily initializes and returns the Supabase service-role client."""
    global _supabase_client
    if _supabase_client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are not configured.")
        _supabase_client = create_client(url, key)
    return _supabase_client


_appconfig_client = None

def get_appconfig() -> AzureAppConfigurationClient:
    """Lazily initializes and returns the Azure App Configuration client."""
    global _appconfig_client
    if _appconfig_client is None:
        conn_str = os.environ.get("AZURE_APP_CONFIG_CONNECTION_STRING")
        if not conn_str:
            raise RuntimeError("AZURE_APP_CONFIG_CONNECTION_STRING is not configured.")
        _appconfig_client = AzureAppConfigurationClient.from_connection_string(conn_str)
    return _appconfig_client


_openai_client = None

def get_openai() -> AzureOpenAI:
    """Lazily initializes and returns the Azure OpenAI client."""
    global _openai_client
    if _openai_client is None:
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2025-03-01-preview")
        if not endpoint or not api_key:
            raise RuntimeError("AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY are not configured.")
        _openai_client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version
        )
    return _openai_client


# ---------------------------------------------------------------------------
# helper functions for AppConfig
# ---------------------------------------------------------------------------

def get_appconfig_value(key: str, default: str) -> str:
    """Helper to get a configuration value with fallback from Azure App Config."""
    try:
        client = get_appconfig()
        setting = client.get_configuration_setting(key=key, label="production")
        return setting.value if setting.value is not None else default
    except Exception as e:
        logger.warning(f"Failed to fetch {key} from AppConfig: {e}. Using default: {default}")
        # Try local environment variable as fallback
        return os.environ.get(key, default)


# ---------------------------------------------------------------------------
# CRON 1: Daily Token Budget Reset (0 0 * * * UTC)
# ---------------------------------------------------------------------------

@app.timer_trigger(schedule="0 0 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=False)
def token_quota_reset(myTimer: func.TimerRequest) -> None:
    utc_timestamp = datetime.now(timezone.utc).isoformat()
    logger.info(f"token_quota_reset cron trigger started at {utc_timestamp}")

    try:
        db = get_supabase()
        
        # 1. Fetch active profiles
        res = db.table("profiles").select("id").eq("is_active", True).execute()
        active_users = res.data or []
        
        # 2. Invoke RPC ensure_budget_row for each user
        count = 0
        for user in active_users:
            user_id = user.get("id")
            if user_id:
                db.rpc("ensure_budget_row", {"p_user_id": user_id}).execute()
                count += 1

        logger.info(f"token_quota_reset completed. Event: token_reset, users_reset: {count}, timestamp: {utc_timestamp}")
    except Exception as e:
        logger.error(f"Error in token_quota_reset: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# CRON 2: Monthly Agent Quota Reset (0 0 1 * * UTC)
# ---------------------------------------------------------------------------

@app.timer_trigger(schedule="0 0 1 * *", arg_name="myTimer", run_on_startup=False, use_monitor=False)
def agent_quota_reset(myTimer: func.TimerRequest) -> None:
    utc_timestamp = datetime.now(timezone.utc).isoformat()
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    logger.info(f"agent_quota_reset cron trigger started at {utc_timestamp} for period {period}")

    try:
        db = get_supabase()
        
        # 1. Fetch active profiles
        res = db.table("profiles").select("id").eq("is_active", True).execute()
        active_users = res.data or []
        
        # 2. Prepare bulk payload
        payload = []
        for user in active_users:
            user_id = user.get("id")
            if user_id:
                payload.append({"user_id": user_id, "period": period})
        
        # 3. Bulk upsert (ON CONFLICT (user_id, period) DO NOTHING)
        if payload:
            db.table("agent_quotas").upsert(payload, on_conflict="user_id,period").execute()

        logger.info(f"agent_quota_reset completed. Event: agent_quota_reset, period: {period}, users_reset: {len(payload)}")
    except Exception as e:
        logger.error(f"Error in agent_quota_reset: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# CRON 3: Hourly Usage Aggregation (0 * * * * UTC)
# ---------------------------------------------------------------------------

@app.timer_trigger(schedule="0 * * * *", arg_name="myTimer", run_on_startup=False, use_monitor=False)
def usage_aggregation(myTimer: func.TimerRequest) -> None:
    utc_timestamp = datetime.now(timezone.utc).isoformat()
    logger.info(f"usage_aggregation cron trigger started at {utc_timestamp}")

    try:
        db = get_supabase()
        
        # Aggregate the last 2 hours to prevent missing any records
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=2)
        
        db.rpc("aggregate_hourly_usage", {
            "p_start": start.isoformat(),
            "p_end": end.isoformat()
        }).execute()

        logger.info(f"usage_aggregation completed. Event: usage_aggregation, start: {start.isoformat()}, end: {end.isoformat()}")
    except Exception as e:
        logger.error(f"Error in usage_aggregation: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# CRON 4: Conversation Archiver (0 2 * * * UTC)
# ---------------------------------------------------------------------------

@app.timer_trigger(schedule="0 2 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=False)
def conversation_archiver(myTimer: func.TimerRequest) -> None:
    utc_timestamp = datetime.now(timezone.utc).isoformat()
    logger.info(f"conversation_archiver cron trigger started at {utc_timestamp}")

    try:
        db = get_supabase()
        
        # Trigger the RPC which runs update and returns row count
        res = db.rpc("archive_stale_conversations").execute()
        count = res.data if res.data is not None else 0

        logger.info(f"conversation_archiver completed. Event: conversations_archived, count: {count}")
    except Exception as e:
        logger.error(f"Error in conversation_archiver: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# CRON 5: Model Expiry Monitor (0 9 * * * UTC)
# ---------------------------------------------------------------------------

@app.timer_trigger(schedule="0 9 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=False)
def model_expiry_monitor(myTimer: func.TimerRequest) -> None:
    utc_timestamp = datetime.now(timezone.utc).isoformat()
    logger.info(f"model_expiry_monitor cron trigger started at {utc_timestamp}")

    modes = ["THINK", "SOLVE", "NANO", "COMPACTION"]
    
    try:
        client = get_appconfig()
        current_date = datetime.now(timezone.utc).date()
        
        for mode in modes:
            expiry_key = f"{mode}_MODEL_EXPIRY_DATE"
            deployment_key = f"{mode}_MODEL_DEPLOYMENT"
            fallback_key = f"{mode}_FALLBACK_DEPLOYMENT"
            
            # 1. Fetch values
            expiry_str = get_appconfig_value(expiry_key, "")
            deployment_val = get_appconfig_value(deployment_key, "")
            fallback_val = get_appconfig_value(fallback_key, "")
            
            if not expiry_str or not deployment_val:
                continue
                
            try:
                expiry_date = datetime.strptime(expiry_str.strip(), "%Y-%m-%d").date()
                days_left = (expiry_date - current_date).days
                
                if days_left <= 0:
                    # Expired -> auto-swap
                    if fallback_val:
                        logger.error(f"CRITICAL: {mode} model deployment {deployment_val} has expired on {expiry_str}! Initiating auto-swap to {fallback_val}...")
                        
                        # Fetch original setting to retain labels/tags
                        setting = client.get_configuration_setting(key=deployment_key, label="production")
                        setting.value = fallback_val
                        client.set_configuration_setting(setting)
                        
                        logger.info(f"model_auto_swap completed. Event: model_auto_swap, mode: {mode}, from: {deployment_val}, to: {fallback_val}")
                    else:
                        logger.critical(f"CRITICAL EXPIRED: {mode} deployment {deployment_val} is expired on {expiry_str}, but no fallback deployment is configured!")
                
                elif days_left <= 7:
                    logger.critical(f"CRITICAL MODEL EXPIRY WARNING: {mode} model {deployment_val} expires in {days_left} days on {expiry_str}!")
                
                elif days_left <= 30:
                    logger.warning(f"MODEL EXPIRY WARNING: {mode} model {deployment_val} expires in {days_left} days on {expiry_str}.")
                    
            except ValueError:
                logger.error(f"Invalid date format for {expiry_key}: '{expiry_str}'. Expected YYYY-MM-DD.")
                
    except Exception as e:
        logger.error(f"Error in model_expiry_monitor: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# CRON 6: Conversation Summarizer / Chat Compaction (0 3 * * * UTC)
# ---------------------------------------------------------------------------

@app.timer_trigger(schedule="0 3 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=False)
def conversation_summarizer(myTimer: func.TimerRequest) -> None:
    utc_timestamp = datetime.now(timezone.utc).isoformat()
    logger.info(f"conversation_summarizer cron trigger started at {utc_timestamp}")

    try:
        db = get_supabase()
        
        # 1. Load config values
        threshold_str = get_appconfig_value("COMPACTION_THRESHOLD", "50")
        compaction_model = get_appconfig_value("COMPACTION_MODEL_DEPLOYMENT", "o4-mini")
        
        try:
            threshold = int(threshold_str)
        except ValueError:
            threshold = 50

        # 2. Find qualifying conversations
        # We query conversations with message count > threshold
        res = db.table("conversations").select("id, title, message_count, last_compacted_at").gt("message_count", threshold).execute()
        conversations = res.data or []
        
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        qualifying = []
        for c in conversations:
            last_compacted = c.get("last_compacted_at")
            if last_compacted:
                try:
                    last_dt = datetime.fromisoformat(last_compacted.replace("Z", "+00:00"))
                    if last_dt >= seven_days_ago:
                        continue  # Skip recently compacted
                except Exception:
                    pass
            qualifying.append(c)
            if len(qualifying) == 20:
                break  # Max 20 per execution batch
        
        if not qualifying:
            logger.info("No conversations met requirements for summarization / compaction.")
            return

        openai_client = get_openai()
        system_prompt = (
            "Summarize this conversation history concisely. Preserve: all decisions made, "
            "key facts, user preferences, ongoing tasks, and any code or data shared. "
            "Output as structured paragraphs. Be thorough but compact."
        )

        for c in qualifying:
            conv_id = c["id"]
            try:
                # Fetch active messages
                msg_res = (
                    db.table("messages")
                    .select("id, role, content")
                    .eq("conversation_id", conv_id)
                    .eq("is_archived_msg", False)
                    .order("created_at", desc=False)
                    .execute()
                )
                messages = msg_res.data or []
                
                if len(messages) < threshold:
                    continue
                
                num_to_archive = int(len(messages) * 0.6)
                old_messages = messages[:num_to_archive]
                
                # Format context
                text_history = ""
                for m in old_messages:
                    role = m.get("role", "unknown")
                    content = m.get("content") or ""
                    text_history += f"{role.upper()}: {content}\n"
                
                # Generate summary via Azure OpenAI Responses API (ADR-002)
                logger.info(f"Requesting summary for conversation {conv_id} using model {compaction_model}...")
                response = openai_client.responses.create(
                    model=compaction_model,
                    input=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": text_history}
                    ]
                )
                summary_content = response.output_text
                
                # 3. DB Transaction Logic (Atomic inserts/updates)
                # a. Insert system summary message
                db.table("messages").insert({
                    "conversation_id": conv_id,
                    "role": "system",
                    "content": summary_content,
                    "is_summary": True,
                    "is_archived_msg": False,
                    "routing_mode": "summary"
                }).execute()
                
                # b. Archive old messages
                old_ids = [m["id"] for m in old_messages]
                db.table("messages").update({"is_archived_msg": True}).in_("id", old_ids).execute()
                
                # c. Update last_compacted_at and active message_count
                new_count = len(messages) - num_to_archive + 1
                db.table("conversations").update({
                    "last_compacted_at": datetime.now(timezone.utc).isoformat(),
                    "message_count": new_count
                }).eq("id", conv_id).execute()
                
                logger.info(f"Compaction completed. Event: compaction, conversation_id: {conv_id}, messages_archived: {num_to_archive}")
                
            except Exception as conv_err:
                logger.error(f"Error compacting conversation {conv_id}: {conv_err}", exc_info=True)
                # Continue with the next conversation in the batch
                
    except Exception as e:
        logger.error(f"Error in conversation_summarizer: {e}", exc_info=True)