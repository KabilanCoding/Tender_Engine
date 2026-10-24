import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router
from app.ai import cloud_clients
from app.ai.llm_client import llm_client
from app.core import runtime_settings
from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
import app.models  # noqa: F401  (registers every model)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The schema is managed by Alembic (run `alembic upgrade head`); the app never alters tables itself.
    try:
        async with AsyncSessionLocal() as db:
            await runtime_settings.load_saved(db)
            from app.api.v1.eligibility import fail_interrupted_runs
            stale = await fail_interrupted_runs(db)
            if stale:
                logging.getLogger(__name__).warning("Marked %s interrupted analysis run(s) as failed", stale)
    except Exception as e:  # e.g. migrations not applied yet: start with defaults and say so
        logging.getLogger(__name__).warning("Could not load saved settings (%s); using defaults", e)
    refresher = asyncio.create_task(runtime_settings.refresh_forever())
    from app.services.tender_tiger.auto_queue import worker_forever
    auto_worker = asyncio.create_task(worker_forever())   # Tender Tiger auto-analysis (does nothing until switched on)
    yield
    auto_worker.cancel()
    refresher.cancel()
    await engine.dispose()


app = FastAPI(
    title="ZYNEX API",
    description="Zero-Cloud, Your-Data, Neural Estimation & eXecution",
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
    return {"status": "ok", "service": "ZYNEX"}


@app.get("/health/ready")
async def ready(response: Response):
    """Readiness: can the app reach the database and the AI service? (used by monitoring and deploy checks)"""
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
        problems = cloud_clients.config_problems(settings.LLM_PROVIDER, "ai")
        checks["ai"] = f"ok ({settings.LLM_PROVIDER} provider)" if not problems else "error: " + "; ".join(problems)
    healthy = all(v.startswith("ok") for v in checks.values())
    if not healthy:
        response.status_code = 503
    return {"status": "ok" if healthy else "degraded", "checks": checks}
