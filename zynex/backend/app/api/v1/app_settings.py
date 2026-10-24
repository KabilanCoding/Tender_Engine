"""Settings page API: read and change everything in settings_registry (admin), plus a public read-only view."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import cloud_clients
from app.ai.llm_client import llm_client
from app.core import file_store, runtime_settings
from app.core import settings_registry as registry
from app.core.config import settings
from app.core.dependencies import get_db
from app.core.security import require_role

router = APIRouter(prefix="/settings", tags=["settings"])

_MODEL_KEYS = ("ai.default_model", "tender.model", "tender.fallback_model")


class SaveBody(BaseModel):
    values: Dict[str, Any]


class LlmProbeBody(BaseModel):
    provider: str
    scope: str = "tender"          # which tab's saved entries to fall back on: "tender" or "ai"
    url: Optional[str] = None
    key: Optional[str] = None      # blank = use the key already saved for this provider
    model: Optional[str] = None


class ResetBody(BaseModel):
    keys: Optional[List[str]] = None     # None = reset everything


def _payload() -> Dict[str, Any]:
    return {"groups": list(registry.GROUPS), "settings": runtime_settings.describe(),
            "nvidia_key_configured": bool(settings.NVIDIA_KEY or settings.NVIDIA_API_KEY)}


async def _check_cross_field_rules(clean: Dict[str, Any]) -> None:
    problems: List[str] = []
    provider = clean.get("ai.provider", settings.LLM_PROVIDER)

    def merged(scope: str, prov: str) -> dict:
        """The provider's saved address/key/model with the values being saved laid on top."""
        current = cloud_clients.settings_for(prov, scope)
        keys = cloud_clients.setting_keys(scope, prov)
        return {f: clean.get(keys[f], current[f]) for f in ("url", "key", "model")}

    if provider in ("nvidia", *cloud_clients.CLOUD_PROVIDERS):
        m = merged("ai", provider)
        problems += cloud_clients.problems_with(provider, m["url"], m["key"], m["model"])
    url = clean.get("ai.ollama_url")
    if url is not None and not url.startswith(("http://", "https://")):
        problems.append("Ollama address: must start with http:// or https://")

    for key, value in clean.items():
        if key.endswith(("_url", "_base_url")) and key.startswith(("tender.", "ai.")) and value and not value.startswith(("http://", "https://")):
            problems.append(f"{registry.BY_KEY[key].label}: must start with http:// or https://")
    chosen_tender = clean.get("tender.provider", settings.TENDER_PROVIDER)
    if chosen_tender in cloud_clients.CLOUD_PROVIDERS:
        m = merged("tender", chosen_tender)
        problems += cloud_clients.problems_with(chosen_tender, m["url"], m["key"], m["model"])

    chosen = [(k, clean[k]) for k in _MODEL_KEYS if clean.get(k)]
    if chosen and provider == "ollama":
        installed = await llm_client.list_models()
        for key, model in chosen:
            if installed and model not in installed:
                problems.append(f"{registry.BY_KEY[key].label}: '{model}' is not installed in Ollama "
                                f"(installed: {', '.join(installed)})")
    if problems:
        raise HTTPException(422, "; ".join(problems))


@router.get("")
async def read_settings(_user: dict = Depends(require_role("admin"))):
    return _payload()


@router.put("")
async def save_settings(body: SaveBody, db: AsyncSession = Depends(get_db),
                        user: dict = Depends(require_role("admin"))):
    try:
        clean = runtime_settings.validate_changes(body.values)
    except registry.SettingValidationError as e:
        raise HTTPException(422, str(e))
    await _check_cross_field_rules(clean)
    await runtime_settings.save(db, clean, int(user.get("sub")) if user.get("sub") else None)
    return _payload()


@router.post("/reset")
async def reset_settings(body: ResetBody, db: AsyncSession = Depends(get_db),
                         _user: dict = Depends(require_role("admin"))):
    unknown = [k for k in (body.keys or []) if k not in registry.BY_KEY]
    if unknown:
        raise HTTPException(422, f"Unknown setting(s): {', '.join(unknown)}")
    await runtime_settings.reset(db, body.keys)
    return _payload()


def _probe_values(body: LlmProbeBody) -> Dict[str, str]:
    scope = body.scope if body.scope in ("tender", "ai") else "tender"
    if body.provider not in ("ollama", *cloud_clients.CLOUD_PROVIDERS) and not (scope == "ai" and body.provider == "nvidia"):
        raise HTTPException(422, "Unknown provider")
    if body.provider == "ollama":
        saved = {"url": (settings.TENDER_OLLAMA_URL if scope == "tender" else "") or settings.OLLAMA_BASE_URL, "key": "", "model": ""}
    else:
        saved = cloud_clients.settings_for(body.provider, scope)
    return {"url": (body.url or saved["url"]).strip(), "key": (body.key or saved["key"]).strip(),
            "model": (body.model or saved["model"]).strip()}


@router.post("/llm/test")
async def test_llm(body: LlmProbeBody, _user: dict = Depends(require_role("admin"))):
    """Check the address, API key and model of one provider with a tiny request (admin only; the key is never returned)."""
    v = _probe_values(body)
    return await cloud_clients.ping(body.provider, v["url"], v["key"], v["model"])


@router.post("/llm/models")
async def list_llm_models(body: LlmProbeBody, _user: dict = Depends(require_role("admin"))):
    """The models a provider offers, to fill the model picker."""
    v = _probe_values(body)
    try:
        if body.provider == "ollama":
            return {"models": await cloud_clients._OllamaAt(v["url"]).list_models(), "error": None}
        problems = cloud_clients.problems_with(body.provider, v["url"], v["key"], "x")
        if problems:
            return {"models": [], "error": "; ".join(problems)}
        return {"models": await cloud_clients.build_client(body.provider, v["url"], v["key"]).list_models(), "error": None}
    except Exception as e:
        return {"models": [], "error": str(e)[:300]}


@router.post("/storage/test")
async def test_storage(_user: dict = Depends(require_role("admin"))):
    """Write, read back and delete a small file in the saved document storage (this machine or the file server)."""
    try:
        return await file_store.check()
    except file_store.StorageError as e:
        return {"ok": False, "location": settings.STORAGE_LOCATION, "error": e.message}


@router.get("/effective")
async def effective_settings(_user: dict = Depends(require_role("admin", "analyst", "viewer"))):
    """The non-sensitive values the screens need (default model, limits, prompts), for every role."""
    return {item["key"]: item["value"] for item in runtime_settings.describe(only_public=True)}
