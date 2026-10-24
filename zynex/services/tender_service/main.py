import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router
from app.ai.llm_client import llm_client
from app.core import runtime_settings
from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
import app.models  # noqa: F401  (registers every model)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        async with AsyncSessionLocal() as db:
            await runtime_settings.load_saved(db)
    except Exception as e:
        logging.getLogger(__name__).warning("Could not load saved settings (%s); using defaults", e)
    refresher = asyncio.create_task(runtime_settings.refresh_forever())
    yield
    refresher.cancel()
    await engine.dispose()


app = FastAPI(
    title="ZYNEX Tender Analysis Service",
    description="Dedicated microservice for tender analysis, OCR, criteria extraction, rule evaluation, and Tender Tiger integration.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.env.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ZYNEX Tender Analysis Service", "port": 8001}


@app.get("/health/ready")
async def ready(response: Response):
    checks = {}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {type(e).__name__}"
    if settings.LLM_PROVIDER == "ollama":
        models = await llm_client.list_models()
        checks["ai"] = f"ok ({len(models)} models)" if models else "error: Ollama unreachable or no models installed"
    else:
        checks["ai"] = "ok (nvidia provider)"
    healthy = all(v.startswith("ok") for v in checks.values())
    if not healthy:
        response.status_code = 503
    return {"status": "ok" if healthy else "degraded", "checks": checks}

