"""Shared LLM call helper for the tender pipeline: model selection, JSON mode, failover."""
from typing import Optional

from app.ai import cloud_clients
from app.ai.llm_client import llm_client
from app.ai.tender.run_options import RunOptions
from app.core.config import settings
from app.services.eligibility import trace


def primary_model(options: Optional[RunOptions] = None) -> Optional[str]:
    """Settings-page choice, else server ELIGIBILITY_MODEL, else None (provider default)."""
    if cloud_clients.is_cloud():
        return cloud_clients.settings_for(cloud_clients.effective_provider())["model"] or None
    if options is not None:
        return options.primary_model
    return settings.ELIGIBILITY_MODEL or None


def fallback_model() -> Optional[str]:
    if cloud_clients.is_cloud():
        return None                     # a cloud provider has one chosen model; the Ollama fallback does not apply
    if settings.ELIGIBILITY_FALLBACK_MODEL:
        return settings.ELIGIBILITY_FALLBACK_MODEL
    if settings.LLM_PROVIDER == "nvidia":
        return settings.NVIDIA_FALLBACK_MODEL or None
    return None


def model_for_attempt(attempt: int, options: Optional[RunOptions] = None) -> Optional[str]:
    """Attempt 0 uses the primary model; later attempts switch to the fallback model if one is set."""
    if attempt >= 1:
        return fallback_model() or primary_model(options)
    return primary_model(options)


async def chat_json(
    system: str,
    user: str,
    schema: dict,
    attempt: int = 0,
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
    options: Optional[RunOptions] = None,
) -> str:
    """One JSON-constrained chat call under the global LLM concurrency cap.

    First attempt asks for schema-constrained output; retries fall back to plain JSON mode in case
    the model/server rejected the schema.
    """
    kwargs = {"json_schema": schema} if attempt == 0 else {"json_mode": True}
    label = "checklist" if system.startswith("You read a tender (RFP") else "eligibility"
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    out_tokens = max_tokens or (options.max_tokens if options else None) or settings.ELIGIBILITY_MAX_TOKENS
    timeout = float(settings.ELIGIBILITY_CHUNK_TIMEOUT_S)
    try:
        target = cloud_clients.cloud_target()
        if target is not None:
            response = await llm_client.run_limited(
                lambda: target.client.chat(messages, model=target.model, temperature=temperature,
                                           max_tokens=out_tokens, timeout=timeout, **kwargs))
        else:
            backend = cloud_clients.tender_ollama_client() or llm_client
            response = await llm_client.run_limited(
                lambda: backend.chat(
                    messages,
                    model=model_for_attempt(attempt, options),
                    temperature=temperature,
                    max_tokens=out_tokens,
                    num_ctx=(options.num_ctx if options else None),
                    timeout=timeout,
                    **kwargs,
                )
            )
    except Exception as e:
        trace.ai_call(f"{label}_attempt{attempt + 1}", system, user, "", error=f"{type(e).__name__}: {e}")
        raise
    trace.ai_call(f"{label}_attempt{attempt + 1}", system, user, response)
    return response
