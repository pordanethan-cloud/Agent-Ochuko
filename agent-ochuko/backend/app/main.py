# app/main.py
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import load_config, get_config, _CONFIG_CACHE
from app.api.v1.endpoints.chat import router as chat_router
from app.api.v1.endpoints.admin import router as admin_router
from app.api.v1.endpoints.admin_appcfg import router as admin_appcfg_router

logger = logging.getLogger("app.main")

# Load configuration eagerly so it is available during module import/setup
logger.info("Eagerly loading application configuration...")
load_config()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lifespan now just logs readiness as config was loaded eagerly
    logger.info("Application lifespan started.")
    yield
    logger.info("Shutting down application...")


app = FastAPI(
    title="Agent Ochuko API",
    description="Production-grade AI Chat backend system built on Azure and Supabase.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware setup
# We load ALLOWED_ORIGINS dynamically from configuration cache
origins_str = _CONFIG_CACHE.get("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
origins = [origin.strip() for origin in origins_str.split(",") if origin.strip()]


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


@app.get("/health")
async def health_check():
    """Simple status check endpoint."""
    return {
        "status": "healthy",
        "environment": await get_config("ENVIRONMENT", "development")
    }
