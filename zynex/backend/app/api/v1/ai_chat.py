"""
POST /ai/chat         — direct offline LLM chat (full response)
POST /ai/chat/stream  — same but streamed as SSE chunks
"""
import json
from typing import Optional
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.ai import cloud_clients
from app.ai.llm_client import llm_client, OllamaUnavailableError
from app.core.config import settings

router = APIRouter(prefix="/ai", tags=["ai-chat"])


@router.get("/status")
async def status():
    """Live state of the AI provider for the status badge: which provider and model, and whether it is usable.
    A cloud provider is judged by its saved configuration; no request is sent to it on every poll."""
    provider = settings.LLM_PROVIDER
    label = cloud_clients.PROVIDER_LABELS.get(provider, provider)
    if provider == "ollama":
        models = await llm_client.list_models()
        return {"provider": provider, "label": label, "local": True, "reachable": bool(models), "models": len(models),
                "model": settings.OLLAMA_MODEL or (models[0] if models else "")}
    cfg = cloud_clients.settings_for(provider, "ai")
    problems = cloud_clients.config_problems(provider, "ai")
    return {"provider": provider, "label": label, "local": False, "reachable": not problems, "models": 0,
            "model": cfg["model"], "problem": "; ".join(problems) or None}


class ChatMessage(BaseModel):
    role: str       # "user" | "assistant" | "system"
    content: str


class ChatBody(BaseModel):
    messages: list[ChatMessage]
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    system_prompt: Optional[str] = None   # prepended as system message if provided


@router.post("/chat")
async def chat(body: ChatBody):
    messages: list[dict] = []

    if body.system_prompt:
        messages.append({"role": "system", "content": body.system_prompt})

    messages.extend([{"role": m.role, "content": m.content} for m in body.messages])

    try:
        reply = await llm_client.chat(
            messages=messages,
            model=body.model or None,
            temperature=body.temperature or 0.7,
        )
        return {"message": reply}
    except OllamaUnavailableError as exc:
        return {"message": f"(AI unavailable: {exc})", "error": True}


@router.post("/chat/stream")
async def chat_stream(body: ChatBody):
    """Stream LLM reply as SSE — yields data: {content} chunks then data: [DONE]."""
    messages: list[dict] = []
    if body.system_prompt:
        messages.append({"role": "system", "content": body.system_prompt})
    messages.extend([{"role": m.role, "content": m.content} for m in body.messages])

    async def event_stream():
        try:
            async for chunk in llm_client.stream_chat(
                messages=messages,
                model=body.model or None,
                temperature=body.temperature or 0.7,
            ):
                yield f"data: {json.dumps({'content': chunk})}\n\n"
        except OllamaUnavailableError as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable Nginx buffering if behind proxy
        },
    )
