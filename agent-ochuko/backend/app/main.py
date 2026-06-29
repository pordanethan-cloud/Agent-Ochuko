# app/main.py
import os
import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import load_config, get_config, _CONFIG_CACHE, start_config_polling, stop_config_polling
from app.api.v1.endpoints.chat import router as chat_router
from app.api.v1.endpoints.admin import router as admin_router
from app.api.v1.endpoints.admin_appcfg import router as admin_appcfg_router
from app.api.v1.endpoints.conversations import router as conversations_router
from app.middleware import (
    MaintenanceGuardMiddleware,
    BlockGuardMiddleware,
    TokenBudgetMiddleware,
    QuotaGuardMiddleware,
    AuditLogMiddleware,
)

logger = logging.getLogger("app.main")

# Load configuration eagerly so it is available during module import/setup
logger.info("Eagerly loading application configuration...")
load_config()

# Track readiness for /ready probe
_app_ready = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _app_ready
    # Lifespan now logs readiness as config was loaded eagerly
    logger.info("Application lifespan started.")
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Middleware Stack ──────────────────────────────────────────────────────
# Registration order: last registered = first to execute.
# Execution order: Maintenance → Block → TokenBudget → Quota → Audit → Handler
app.add_middleware(AuditLogMiddleware)
app.add_middleware(QuotaGuardMiddleware)
app.add_middleware(TokenBudgetMiddleware)
app.add_middleware(BlockGuardMiddleware)
app.add_middleware(MaintenanceGuardMiddleware)

# Include API routers
app.include_router(chat_router, prefix="/v1", tags=["chat"])
app.include_router(admin_router, prefix="/v1/admin", tags=["admin"])
app.include_router(admin_appcfg_router, prefix="/v1/admin", tags=["admin"])
app.include_router(conversations_router, prefix="/v1/conversations", tags=["conversations"])


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

