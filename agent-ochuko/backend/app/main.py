# app/main.py
import os
import time
import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import load_config, get_config, _CONFIG_CACHE, start_config_polling, stop_config_polling
from app.api.v1.endpoints.chat import router as chat_router
from app.api.v1.endpoints.admin import router as admin_router
from app.api.v1.endpoints.admin_appcfg import router as admin_appcfg_router
from app.api.v1.endpoints.conversations import router as conversations_router
from app.api.v1.endpoints.files import router as files_router
from app.api.v1.endpoints.agents import router as agents_router
from app.api.v1.endpoints.search import router as search_router
from app.api.v1.endpoints.audio import router as audio_router
from app.api.v1.endpoints.shared import router as shared_router
from app.middleware import (
    MaintenanceGuardMiddleware,
    BlockGuardMiddleware,
    TokenBudgetMiddleware,
    QuotaGuardMiddleware,
    AuditLogMiddleware,
)

logger = logging.getLogger("app.main")

# Track readiness for /ready probe
_app_ready = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _app_ready
    logger.info("Application lifespan started.")
    
    # Asynchronously warm up backend configurations and API connection pools
    async def warm_up_resources():
        try:
            # 1. Load Azure App Configuration in background thread executor
            loop = asyncio.get_running_loop()
            logger.info("Lifespan: Loading application configuration from Azure App Config...")
            await loop.run_in_executor(None, load_config)
            logger.info("Lifespan: Application configuration loaded successfully.")
            
            # 2. Warm up Azure OpenAI Async Client connection pool
            from app.api.v1.endpoints.chat import get_openai_client
            get_openai_client()
            logger.info("Lifespan: Eagerly warmed up Azure OpenAI client pool.")
        except Exception as err:
            logger.warning(f"Lifespan: Background resource warmup failed: {err}")

    # Spawn resource warm up concurrently in the background (non-blocking)
    asyncio.create_task(warm_up_resources())

    # Pre-warm the Supabase JWKS token signature cache in the background (non-blocking)
    supabase_url = os.getenv("SUPABASE_URL")
    if supabase_url:
        try:
            from app.core.jwt_validator import get_jwks
            # Use asyncio.create_task to run the pre-warming concurrently in the background
            # so it does not block the FastAPI server boot or container readiness probes.
            asyncio.create_task(get_jwks(supabase_url))
            logger.info("Lifespan: Spawned background task to pre-warm JWKS cache.")
        except Exception as jwks_err:
            logger.warning(f"Lifespan: Failed to spawn JWKS pre-warming task: {jwks_err}")

    _app_ready = True
    start_config_polling(300)
    yield
    stop_config_polling()
    _app_ready = False
    logger.info("Shutting down application...")


app = FastAPI(
    title="Agent Ochuko API",
    description="Production-grade AI Chat backend system built on Azure and Supabase.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware setup
origins_str = _CONFIG_CACHE.get("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
env_origins = os.getenv("ALLOWED_ORIGINS")

combined_origins = set()
for o in origins_str.split(","):
    if o.strip():
        combined_origins.add(o.strip())
if env_origins:
    for o in env_origins.split(","):
        if o.strip():
            combined_origins.add(o.strip())

origins = list(combined_origins)

# Auto-include production deployed storage static website domains
prod_origins = [
    "https://agentochukostore.z1.web.core.windows.net",
    "https://agentochukoadmin.z1.web.core.windows.net"
]
for po in prod_origins:
    if po not in origins:
        origins.append(po)

# ── Middleware Stack ──────────────────────────────────────────────────────
# Registration order: last registered = first to execute (Starlette LIFO).
# Execution order: CORS → Maintenance → Block → TokenBudget → Quota → Audit → Handler
# CRITICAL: AuditLog/Guards registered first (run last), CORS registered last (runs first).
# If CORS runs after a guard, preflight OPTIONS requests get rejected without CORS headers.
app.add_middleware(AuditLogMiddleware)
app.add_middleware(QuotaGuardMiddleware)
app.add_middleware(TokenBudgetMiddleware)
app.add_middleware(BlockGuardMiddleware)
app.add_middleware(MaintenanceGuardMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(chat_router, prefix="/v1", tags=["chat"])
app.include_router(admin_router, prefix="/v1/admin", tags=["admin"])
app.include_router(admin_appcfg_router, prefix="/v1/admin", tags=["admin"])
app.include_router(conversations_router, prefix="/v1/conversations", tags=["conversations"])
app.include_router(files_router, prefix="/v1/files", tags=["files"])
app.include_router(agents_router, prefix="/v1/agents", tags=["agents"])
app.include_router(search_router, prefix="/v1/search", tags=["search"])
app.include_router(audio_router, prefix="/v1/audio", tags=["audio"])  # voice-to-text transcriptions
app.include_router(shared_router, prefix="/v1/shared", tags=["shared"])


# ── Health & Readiness Probes ─────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """
    Deep health check — pings Supabase and Azure OpenAI with 2s timeouts.
    Used by Azure Container Apps as the liveness probe.
    Returns 503 if any critical service is unreachable.
    """
    import httpx

    checks = {}
    overall_healthy = True

    # Check Supabase
    supabase_url = os.getenv("SUPABASE_URL")
    if supabase_url:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{supabase_url}/auth/v1/health")
                checks["supabase"] = "ok" if resp.status_code < 500 else "degraded"
        except Exception:
            checks["supabase"] = "unreachable"
            overall_healthy = False
    else:
        checks["supabase"] = "not_configured"

    # Check Azure OpenAI (lightweight — just verify endpoint is reachable)
    openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if openai_endpoint:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(openai_endpoint)
                # Azure OpenAI returns various status codes — anything not 5xx is fine
                checks["azure_openai"] = "ok" if resp.status_code < 500 else "degraded"
        except Exception:
            checks["azure_openai"] = "unreachable"
            overall_healthy = False
    else:
        checks["azure_openai"] = "not_configured"

    # Check App Config cache (in-memory — just verify it loaded)
    checks["app_config"] = "ok" if len(_CONFIG_CACHE) > 5 else "degraded"

    status_code = 200 if overall_healthy else 503
    return {
        "status": "healthy" if overall_healthy else "degraded",
        "version": "1.0.0",
        "environment": await get_config("ENVIRONMENT", "development"),
        "checks": checks,
    }


@app.get("/ready")
async def readiness_check():
    """
    Readiness probe — returns 200 only when config is loaded and app is ready.
    Azure Container Apps won't route traffic until this returns 200.
    """
    if not _app_ready:
        return {"status": "not_ready"}, 503

    if len(_CONFIG_CACHE) < 3:
        return {"status": "config_not_loaded"}, 503

    return {"status": "ready"}

