import os
import json
import logging
import itertools
from datetime import datetime, timezone, timedelta
import socket
import urllib.request
import azure.functions as func
from supabase import create_client, Client
from azure.appconfiguration import AzureAppConfigurationClient
from openai import AzureOpenAI

# ── DNS-over-HTTPS monkeypatch to bypass regional Azure DNS limitations ────
def resolve_dns_doh(hostname: str) -> str:
    # Try Google DoH first (via direct IP to avoid bootstrap DNS lookup)
    try:
        url = f"https://8.8.8.8/resolve?name={hostname}&type=1"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=3.0) as response:
            res_data = json.loads(response.read().decode())
            if "Answer" in res_data:
                for answer in res_data["Answer"]:
                    if answer.get("type") == 1:  # Type A
                        return answer.get("data")
    except Exception as e:
        logging.warning(f"Google DNS DoH resolution failed for {hostname}: {e}")

    # Try Cloudflare DoH fallback (via direct IP to avoid bootstrap DNS lookup)
    try:
        url = f"https://1.1.1.1/dns-query?name={hostname}&type=A"
        req = urllib.request.Request(url, headers={"Accept": "application/dns-json"})
        with urllib.request.urlopen(req, timeout=3.0) as response:
            res_data = json.loads(response.read().decode())
            if "Answer" in res_data:
                for answer in res_data["Answer"]:
                    if answer.get("type") == 1:  # Type A
                        return answer.get("data")
    except Exception as e:
        logging.warning(f"Cloudflare DNS DoH resolution failed for {hostname}: {e}")
        
    return None

_original_getaddrinfo = socket.getaddrinfo

def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host == "router.huggingface.co":
        ip = resolve_dns_doh(host)
        if ip:
            logging.info(f"DNS Patched: resolved {host} to {ip}")
            return _original_getaddrinfo(ip, port, family, type, proto, flags)
    return _original_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = patched_getaddrinfo
# ───────────────────────────────────────────────────────────────────────────


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
# Image Prompt Expander (Responses API)
# ---------------------------------------------------------------------------

IMAGE_PROMPT_EXPANDER_SYSTEM_PROMPT = """
Role: Expert AI Image Prompt Director for the FLUX.1-dev text-to-image diffusion model.
Task: Transform a short user request into a technically precise, visually rich image generation prompt that FLUX will render faithfully.

CRITICAL RULES (follow literally, in order):
1. Read the user's request. Identify the core subject, even if only implied. Never ask for clarification — infer intent.
2. FRONT-LOAD THE SUBJECT. FLUX weights early tokens most heavily. The first 10-15 words must name and describe the primary subject.
3. Expand across exactly four layers: subject, environment, lighting_and_composition, artistic_style.
4. For each layer, use concrete technical vocabulary:
   - Camera: lens focal length (85mm f/1.4, 35mm anamorphic, macro 100mm), depth of field, angle (low angle, bird's eye, Dutch tilt)
   - Lighting: rim light, volumetric haze, golden hour side-light, overcast diffused, studio three-point, neon underglow
   - Materials/textures: brushed steel, matte cotton, subsurface scattering on skin, wet asphalt reflections, frosted glass
   - Composition: rule of thirds, centered symmetry, leading lines, negative space, foreground bokeh
5. BANNED WORDS (FLUX treats these as noise): photorealistic, hyperdetailed, 8k, 4k, stunning, beautiful, epic, masterpiece, best quality, highly detailed, ultra, award-winning. Instead describe the specific optical or material property.
6. Keep total length of final_expanded_prompt between 40 and 180 words. Under 40 produces generic results; over 180 causes prompt degradation.
7. If the user's request implies content that is sexual, violent toward real people, or depicts a real identifiable person, set "rejected": true with a one-line reason and provide an empty final_expanded_prompt.
8. For abstract concepts (e.g., "freedom", "happiness"), translate them into a concrete visual metaphor scene.

OUTPUT FORMAT: Return ONLY a raw JSON object. No markdown fences, no preamble, no commentary.
Schema: {"subject": string, "environment": string, "lighting_and_composition": string, "artistic_style": string, "final_expanded_prompt": string, "rejected": boolean, "reason": string}
""".strip()

def _expand_prompt(prompt: str) -> dict:
    """
    Expands a basic prompt into a structured FLUX prompt using Azure OpenAI Responses API.
    Retries once on JSON parse failure.
    """
    deployment = get_appconfig_value("PROMPT_EXPANDER_MODEL_DEPLOYMENT", "gpt-5.4-mini")
    openai_client = get_openai()
    
    for attempt in range(2):
        try:
            logger.info(f"Running prompt expansion via deployment {deployment} (attempt {attempt+1}/2)...")
            response = openai_client.responses.create(
                model=deployment,
                input=[
                    {"role": "system", "content": IMAGE_PROMPT_EXPANDER_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ]
            )
            raw_text = (response.output_text or "").strip()
            if raw_text.startswith("```"):
                lines = raw_text.splitlines()
                if len(lines) > 2:
                    raw_text = "\n".join(lines[1:-1]).strip()
            
            data = json.loads(raw_text)
            if "final_expanded_prompt" in data and "rejected" in data:
                return data
            
            raise ValueError("Parsed JSON missing required keys: 'final_expanded_prompt' or 'rejected'.")
        except Exception as e:
            logger.warning(f"Prompt expansion attempt {attempt+1} failed: {e}")
            if attempt == 1:
                return {
                    "subject": prompt,
                    "environment": "",
                    "lighting_and_composition": "",
                    "artistic_style": "",
                    "final_expanded_prompt": prompt,
                    "rejected": False,
                    "reason": str(e)
                }


# ---------------------------------------------------------------------------
# CRON 1: Daily Token Budget Reset (0 0 * * * UTC)
# ---------------------------------------------------------------------------

@app.timer_trigger(schedule="0 23 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=False)
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

@app.timer_trigger(schedule="0 23 1 * *", arg_name="myTimer", run_on_startup=False, use_monitor=False)
def agent_quota_reset(myTimer: func.TimerRequest) -> None:
    wat = timezone(timedelta(hours=1))
    now_wat = datetime.now(wat)
    if now_wat.day != 1:
        # Only run on the 1st day of the month in WAT (Nigerian Time)
        return

    utc_timestamp = datetime.now(timezone.utc).isoformat()
    period = now_wat.strftime("%Y-%m")
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


# ===========================================================================
# Background Agent Task Queue Worker (Pattern B)
# ===========================================================================

_doc_client = None

def get_doc_client():
    """Lazily initializes the Azure Document Intelligence client."""
    global _doc_client
    if _doc_client is None:
        from azure.ai.formrecognizer import DocumentAnalysisClient
        from azure.core.credentials import AzureKeyCredential
        
        endpoint = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
        key = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_KEY")
        if not endpoint or not key:
            raise RuntimeError("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and AZURE_DOCUMENT_INTELLIGENCE_KEY must be configured.")
        _doc_client = DocumentAnalysisClient(endpoint, AzureKeyCredential(key))
    return _doc_client


_vision_client = None

def get_vision_client():
    """Lazily initializes the Azure Computer Vision client."""
    global _vision_client
    if _vision_client is None:
        from azure.cognitiveservices.vision.computervision import ComputerVisionClient
        from msrest.authentication import CognitiveServicesCredentials
        
        endpoint = os.environ.get("AZURE_VISION_ENDPOINT")
        key = os.environ.get("AZURE_VISION_KEY")
        if not endpoint or not key:
            raise RuntimeError("AZURE_VISION_ENDPOINT and AZURE_VISION_KEY must be configured.")
        _vision_client = ComputerVisionClient(endpoint, CognitiveServicesCredentials(key))
    return _vision_client


# Round-robin iterator over HuggingFace API keys for load distribution
_hf_key_cycle = None

def _get_next_hf_key() -> str:
    """Returns the next HuggingFace API key from the comma-separated pool, cycling round-robin."""
    global _hf_key_cycle
    if _hf_key_cycle is None:
        raw = os.environ.get("HUGGINGFACE_API_KEYS", "")
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        if not keys:
            raise RuntimeError("HUGGINGFACE_API_KEYS is not configured.")
        _hf_key_cycle = itertools.cycle(keys)
    return next(_hf_key_cycle)


def _upload_image_to_blob(image_bytes: bytes, blob_name: str) -> str:
    """
    Uploads raw image bytes to the 'agent-outputs' container in Azure Blob Storage.
    Returns the public blob URL (without SAS — container must allow public read or
    a separate SAS read URL is generated as needed by the frontend).
    """
    from azure.storage.blob import BlobServiceClient
    conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not conn_str:
        raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is not configured.")

    blob_service = BlobServiceClient.from_connection_string(conn_str)
    container_name = "agent-outputs"

    # Ensure container exists (no-op if already present)
    container_client = blob_service.get_container_client(container_name)
    try:
        container_client.create_container()
    except Exception:
        pass  # Already exists

    from azure.storage.blob import ContentSettings
    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(
        image_bytes, overwrite=True,
        content_settings=ContentSettings(content_type="image/png")
    )

    account_name = blob_service.account_name
    return f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}"


def _upload_to_r2(data: bytes, filename: str, content_type: str, bucket_type: str = "UPLOADS") -> str:
    """
    Uploads raw bytes to Cloudflare R2 bucket.
    Returns the public URL using R2_PUBLIC_DOMAIN.
    """
    import boto3
    from botocore.config import Config

    prefix = f"R2_{bucket_type.upper()}_"

    access_key = os.environ.get(f"{prefix}ACCESS_KEY_ID")
    secret_key = os.environ.get(f"{prefix}SECRET_ACCESS_KEY")
    endpoint = os.environ.get(f"{prefix}ENDPOINT")
    bucket_name = os.environ.get(f"{prefix}BUCKET_NAME")
    public_domain = os.environ.get(f"{prefix}PUBLIC_DOMAIN")

    # Fallback to default credentials
    if not all([access_key, secret_key, endpoint]):
        access_key = os.environ.get("R2_ACCESS_KEY_ID")
        secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
        endpoint = os.environ.get("R2_ENDPOINT")
        bucket_name = os.environ.get("R2_BUCKET_NAME", "octal-ehr-files")
        public_domain = os.environ.get("R2_PUBLIC_DOMAIN", "https://pub-3aabaa1c09b9c0da240f1ae5ed8d8478.r2.dev")

    if not access_key or not secret_key or not endpoint:
        raise RuntimeError("Cloudflare R2 configuration credentials are not configured.")

    # Create boto3 client for R2 (S3-compatible)
    s3_client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4")
    )

    s3_client.put_object(
        Bucket=bucket_name,
        Key=filename,
        Body=data,
        ContentType=content_type
    )

    domain = public_domain.rstrip("/")
    filename = filename.lstrip("/")
    return f"{domain}/{filename}"




def get_read_sas_url(blob_url: str) -> str:
    """Generates a short-lived read-only SAS URL for the given direct blob URL."""
    # Check if this is an R2 URL (or not an Azure Blob URL)
    if ".blob.core.windows.net/" not in blob_url:
        try:
            import boto3
            from botocore.config import Config
            
            access_key = os.environ.get("R2_ACCESS_KEY_ID")
            secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
            endpoint = os.environ.get("R2_ENDPOINT")
            bucket_name = os.environ.get("R2_BUCKET_NAME", "agent-ochuko-storage")
            public_domain = os.environ.get("R2_PUBLIC_DOMAIN", "")
            
            if access_key and secret_key and endpoint:
                s3_client = boto3.client(
                    "s3",
                    endpoint_url=endpoint,
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                    config=Config(signature_version="s3v4")
                )
                
                # Parse the R2 Key from the URL
                r2_domain_host = public_domain.split("://")[-1].split("/")[0] if public_domain else ""
                if r2_domain_host and r2_domain_host in blob_url:
                    key = blob_url.split(r2_domain_host)[-1].lstrip("/")
                else:
                    # Fallback parser if domain doesn't match
                    key = "/".join(blob_url.split("://")[-1].split("/")[1:])
                
                presigned_url = s3_client.generate_presigned_url(
                    ClientMethod="get_object",
                    Params={
                        "Bucket": bucket_name,
                        "Key": key
                    },
                    ExpiresIn=3600  # 1 hour
                )
                return presigned_url
        except Exception as e:
            logger.warning(f"Failed to generate R2 presigned GET URL: {e}")
        return blob_url

    conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not conn_str:
        return blob_url  # Fallback if connection string is missing

    try:
        from azure.storage.blob import generate_blob_sas, BlobSasPermissions
        
        # Extract AccountName and AccountKey
        parts = {}
        for item in conn_str.split(';'):
            if '=' in item:
                k, v = item.split('=', 1)
                parts[k.strip()] = v.strip()
        account_name = parts.get("AccountName")
        account_key = parts.get("AccountKey")

        if not account_name or not account_key:
            return blob_url

        # Parse container and blob name from URL
        url_parts = blob_url.split(".blob.core.windows.net/")
        if len(url_parts) < 2:
            return blob_url

        path_parts = url_parts[1].split("/", 1)
        if len(path_parts) < 2:
            return blob_url

        container_name = path_parts[0]
        blob_name = path_parts[1]

        permissions = BlobSasPermissions(read=True)
        expiry = datetime.now(timezone.utc) + timedelta(hours=1)

        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container_name,
            blob_name=blob_name,
            account_key=account_key,
            permission=permissions,
            expiry=expiry
        )
        return f"{blob_url}?{sas_token}"
    except Exception as e:
        logger.warning(f"Failed to generate read SAS URL: {e}")
        return blob_url


@app.queue_trigger(arg_name="msg", queue_name="agent-jobs", connection="AZURE_STORAGE_CONNECTION_STRING")
def agent_jobs_trigger(msg: func.QueueMessage) -> None:
    """
    Queue trigger that processes incoming background agent tasks (OCR, Vision).
    Reads task details, executes cognitive API operations, and updates Supabase state.
    """
    utc_timestamp = datetime.now(timezone.utc).isoformat()
    logger.info(f"agent_jobs_trigger started at {utc_timestamp}")

    try:
        raw = msg.get_body().decode("utf-8").strip()
        # queue_dispatcher.py base64-encodes the JSON payload before enqueuing
        import base64 as _b64
        try:
            decoded = _b64.b64decode(raw).decode("utf-8")
        except Exception:
            decoded = raw  # fallback: not base64, try raw JSON directly
        payload = json.loads(decoded)
    except Exception as parse_err:
        logger.error(f"Failed to parse queue message payload: {parse_err}")
        return

    job_id = payload.get("job_id")
    job_type = payload.get("type")
    input_metadata = payload.get("input_metadata") or {}
    user_id = payload.get("user_id")

    if not job_id or not job_type:
        logger.error("Missing job_id or type in queue message payload.")
        return

    try:
        db = get_supabase()

        # Update job to processing
        db.table("jobs").update({
            "status": "processing",
            "started_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", job_id).execute()

        blob_url = input_metadata.get("blob_url", "")
        read_sas_url = get_read_sas_url(blob_url) if blob_url else ""

        result_data = {}

        if job_type == "ocr":
            if not read_sas_url:
                raise ValueError("Missing blob_url in input_metadata.")

            logger.info(f"Running Document Intelligence OCR on: {blob_url}")
            doc_client = get_doc_client()
            poller = doc_client.begin_analyze_document_from_url("prebuilt-layout", read_sas_url)
            analysis_result = poller.result()

            # Format layout text content
            extracted_lines = []
            for page in analysis_result.pages:
                for line in page.lines:
                    extracted_lines.append(line.content)

            text_content = "\n".join(extracted_lines)
            pages_count = len(analysis_result.pages)
            result_data = {
                "text": text_content,
                "pages": pages_count,
                "confidence": 1.0
            }

            # Increment user's monthly OCR quota
            period = datetime.now(timezone.utc).strftime("%Y-%m")
            quota_res = db.table("agent_quotas").select("ocr_pages_used").eq("user_id", user_id).eq("period", period).maybe_single().execute()
            if quota_res and hasattr(quota_res, "data") and quota_res.data:
                current_pages = quota_res.data.get("ocr_pages_used", 0)
                db.table("agent_quotas").update({
                    "ocr_pages_used": current_pages + pages_count
                }).eq("user_id", user_id).eq("period", period).execute()
            else:
                db.table("agent_quotas").insert({
                    "user_id": user_id,
                    "period": period,
                    "ocr_pages_used": pages_count
                }).execute()

        elif job_type == "vision":
            if not read_sas_url:
                raise ValueError("Missing blob_url in input_metadata.")

            prompt = input_metadata.get("prompt", "Describe the content in this image.")
            logger.info(f"Running Azure OpenAI Vision analysis on: {blob_url} with prompt: {prompt}")

            openai_client = get_openai()
            # Retrieve solve deployment from App Configuration (falls back to gpt-5.4-mini)
            model_deployment = get_appconfig_value("SOLVE_MODEL_DEPLOYMENT", "gpt-5.4-mini")

            # Call Azure OpenAI Chat Completion with the SAS image URL
            response = openai_client.chat.completions.create(
                model=model_deployment,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are Ochuko, an elite enterprise AI assistant. "
                            "Analyze the image and user instructions with confidence and clinical precision. "
                            "Make reasonable assumptions on ambiguous details rather than asking clarifying questions. "
                            "Do not moralize, lecture, or add unnecessary warnings/disclaimers. "
                            "Be direct, crisp, and professional."
                        )
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text", 
                                "text": (
                                    "Analyze this image in detail. If there is text in the image, "
                                    "transcribe all of it accurately. If it is a diagram or document, "
                                    "explain its structure and contents. User instructions: " + prompt
                                )
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": read_sas_url
                                }
                            }
                        ]
                    }
                ],
                max_completion_tokens=800
            )

            description = response.choices[0].message.content

            result_data = {
                "text": description
            }

            # Increment user's monthly Vision quota
            period = datetime.now(timezone.utc).strftime("%Y-%m")
            quota_res = db.table("agent_quotas").select("vision_calls_used").eq("user_id", user_id).eq("period", period).maybe_single().execute()
            if quota_res and hasattr(quota_res, "data") and quota_res.data:
                current_calls = quota_res.data.get("vision_calls_used", 0)
                db.table("agent_quotas").update({
                    "vision_calls_used": current_calls + 1
                }).eq("user_id", user_id).eq("period", period).execute()
            else:
                db.table("agent_quotas").insert({
                    "user_id": user_id,
                    "period": period,
                    "vision_calls_used": 1
                }).execute()

        elif job_type == "image_gen":
            import requests as _requests

            prompt = input_metadata.get("prompt", "")
            style = input_metadata.get("style", "photorealistic")
            if not prompt:
                raise ValueError("Missing prompt in input_metadata for image_gen job.")

            # Expand the prompt using Azure OpenAI responses API
            expanded = _expand_prompt(prompt)
            if expanded.get("rejected"):
                reason = expanded.get("reason", "Prompt rejected by expander guidelines.")
                raise ValueError(f"Prompt expansion rejected: {reason}")

            full_prompt = expanded.get("final_expanded_prompt", prompt)
            logger.info(f"Running HuggingFace FLUX image generation. prompt: {full_prompt[:80]}")

            # Cycle through models and keys on failure as per IMPLEMENTATION_PLAN.md
            raw_models = os.environ.get("HUGGINGFACE_IMAGE_MODEL", "black-forest-labs/FLUX.1-dev")
            model_sequence = [m.strip() for m in raw_models.split(",") if m.strip()]
            if not model_sequence:
                model_sequence = ["black-forest-labs/FLUX.1-dev"]

            # Additional fallback options specified in implementation plan
            for fallback_model in [
                "black-forest-labs/FLUX.1-schnell",
                "SG161222/RealVisXL_V4.0",
                "stabilityai/sdxl-turbo",
                "Lykon/dreamshaper-8",
                "stabilityai/stable-diffusion-2-1"
            ]:
                if fallback_model not in model_sequence:
                    model_sequence.append(fallback_model)

            raw_keys = os.environ.get("HUGGINGFACE_API_KEYS", "")
            keys_pool = [k.strip() for k in raw_keys.split(",") if k.strip()]
            max_keys = max(1, len(keys_pool))

            hf_response = None
            last_error = None

            # Loop through the model hierarchy
            for model_id in model_sequence:
                logger.info(f"Attempting image generation with model: {model_id}")
                hf_api_url = f"https://router.huggingface.co/hf-inference/models/{model_id}"

                # Try all available keys for this model
                for attempt in range(1, max_keys + 1):
                    hf_key = _get_next_hf_key()
                    masked_key = f"{hf_key[:6]}...{hf_key[-4:]}" if len(hf_key) > 10 else "short_key"
                    logger.info(f"Using HuggingFace key {masked_key} (attempt {attempt}/{max_keys}) for model {model_id}...")

                    try:
                        res = _requests.post(
                            hf_api_url,
                            headers={
                                "Authorization": f"Bearer {hf_key}",
                                "Content-Type": "application/json",
                            },
                            json={"inputs": full_prompt},
                            timeout=120,
                        )

                        if res.status_code == 200:
                            hf_response = res
                            break
                        else:
                            logger.warning(
                                f"Key {masked_key} failed for model {model_id} with status {res.status_code}: {res.text[:150]}"
                            )
                            last_error = f"Model {model_id} with key {masked_key} returned {res.status_code}: {res.text[:150]}"
                    except Exception as e:
                        logger.warning(f"Request failed for model {model_id} with key {masked_key}: {e}")
                        last_error = f"Model {model_id} error: {str(e)}"

                if hf_response:
                    logger.info(f"Image generation succeeded using model: {model_id}")
                    break

            if not hf_response:
                raise RuntimeError(
                    f"All HuggingFace models and keys exhausted or rate-limited. Last error: {last_error}"
                )

            image_bytes = hf_response.content
            if not image_bytes or len(image_bytes) < 1000:
                raise RuntimeError("HuggingFace returned an empty or invalid image response.")

            # Save a local copy to the user's Pictures folder if running locally
            try:
                pictures_dir = os.path.expanduser("~/Pictures")
                if os.path.exists(pictures_dir):
                    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                    local_filename = f"ochuko_{job_id}_{timestamp}.png"
                    local_path = os.path.join(pictures_dir, local_filename)
                    with open(local_path, "wb") as f:
                        f.write(image_bytes)
                    logger.info(f"Saved a local copy of the generated image to: {local_path}")
            except Exception as save_local_err:
                logger.warning(f"Could not save copy to local Pictures folder: {save_local_err}")

            # Upload PNG to Cloudflare R2
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"generated/{user_id}/{job_id}_{timestamp}.png"
            image_url = _upload_to_r2(image_bytes, filename, "image/png", bucket_type="IMAGES")



            result_data = {
                "image_url": image_url,
                "prompt": prompt,
                "style": style,
                "expanded_prompt": full_prompt,
                "subject": expanded.get("subject", ""),
                "environment": expanded.get("environment", ""),
                "lighting_and_composition": expanded.get("lighting_and_composition", ""),
                "artistic_style": expanded.get("artistic_style", "")
            }

            # Update the message in the messages table containing this job_id
            try:
                msg_res = (
                    db.table("messages")
                    .select("id, content_parts")
                    .contains("content_parts", {"image_jobs": [{"job_id": job_id}]})
                    .execute()
                )
                if msg_res and hasattr(msg_res, "data") and msg_res.data:
                    for msg in msg_res.data:
                        msg_id = msg.get("id")
                        parts = msg.get("content_parts") or {}
                        jobs_list = parts.get("image_jobs") or []
                        updated_jobs = []
                        for job in jobs_list:
                            if job.get("job_id") == job_id:
                                job["status"] = "done"
                                job["image_url"] = image_url
                            updated_jobs.append(job)
                        parts["image_jobs"] = updated_jobs
                        db.table("messages").update({"content_parts": parts}).eq("id", msg_id).execute()
                        logger.info("Updated message %s content_parts with generated image url: %s", msg_id, image_url)
            except Exception as msg_update_err:
                logger.error("Failed to update message content_parts with image url: %s", msg_update_err)

            # Increment monthly image_gen quota
            period = datetime.now(timezone.utc).strftime("%Y-%m")
            quota_res = db.table("agent_quotas").select("image_gen_used").eq("user_id", user_id).eq("period", period).maybe_single().execute()
            if quota_res and hasattr(quota_res, "data") and quota_res.data:
                current = quota_res.data.get("image_gen_used", 0) or 0
                db.table("agent_quotas").update({"image_gen_used": current + 1}).eq("user_id", user_id).eq("period", period).execute()
            else:
                db.table("agent_quotas").upsert({"user_id": user_id, "period": period, "image_gen_used": 1}, on_conflict="user_id,period").execute()

            logger.info("Image generated and uploaded. job_id=%s url=%.80s", job_id, image_url)

        else:
            raise ValueError(f"Unsupported job type: '{job_type}'")

        # Save done result
        db.table("jobs").update({
            "status": "done",
            "result": result_data,
            "completed_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", job_id).execute()

        logger.info(f"Job {job_id} ({job_type}) finished processing successfully.")

    except Exception as job_err:
        original_error_msg = str(job_err)
        logger.error(f"Failed to process job {job_id} ({job_type}): {original_error_msg}", exc_info=True)
        try:
            db = get_supabase()
            new_retries = 1
            try:
                job_res = db.table("jobs").select("retry_count").eq("id", job_id).maybe_single().execute()
                if job_res and hasattr(job_res, "data") and job_res.data:
                    new_retries = job_res.data.get("retry_count", 0) + 1
            except Exception as read_err:
                logger.warning(f"Failed to read current retry count: {read_err}")

            update_data = {
                "retry_count": new_retries,
                "status": "failed",
                "error": original_error_msg,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }
            db.table("jobs").update(update_data).eq("id", job_id).execute()
        except Exception as db_err:
            logger.error(f"Failed to record job failure for job {job_id}: {db_err}")