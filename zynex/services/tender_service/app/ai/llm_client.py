"""Provider-switching LLM client.

LLM_PROVIDER=ollama (default) keeps everything local/offline.
LLM_PROVIDER=nvidia|openai|anthropic|grok|custom sends text generation/chat to that cloud API
(opt-in; needs an API key saved on the Settings page and outbound network access).

Embeddings always use local Ollama so stored pgvector vectors stay consistent.
"""
import asyncio
import json
import re
from typing import AsyncGenerator, Optional

import httpx

from app.ai import cloud_clients
from app.ai.ollama_client import OllamaUnavailableError, http_timeout, ollama_client, post_with_retry
from app.core.config import settings


class LLMUnavailableError(OllamaUnavailableError):
    """Raised when the active provider cannot be reached. Subclasses the Ollama
    error so existing `except OllamaUnavailableError` handlers keep working."""


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class NvidiaClient:
    """Minimal OpenAI-compatible chat client for NVIDIA's hosted API (no extra SDK)."""

    @property
    def base_url(self) -> str:
        return settings.NVIDIA_BASE_URL.rstrip("/")

    @property
    def default_model(self) -> str:
        return settings.NVIDIA_MODEL

    def _headers(self) -> dict:
        key = settings.NVIDIA_KEY or settings.NVIDIA_API_KEY
        if not key:
            raise LLMUnavailableError("The NVIDIA API key is not set (Settings > AI Model).")
        return {"Authorization": f"Bearer {key}"}

    async def list_models(self) -> list[str]:
        models = [settings.NVIDIA_MODEL, settings.NVIDIA_FALLBACK_MODEL]
        return [m for i, m in enumerate(models) if m and m not in models[:i]]

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        timeout: float = 120.0,
        json_mode: bool = False,
        json_schema: Optional[dict] = None,
        **_ignored,  # num_ctx etc. are Ollama-specific
    ) -> str:
        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_schema:
            # NVIDIA NIM guided decoding; models without support reject it (handled below)
            payload["nvext"] = {"guided_json": json_schema}
        elif json_mode:
            payload["response_format"] = {"type": "json_object"}
        url = f"{self.base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=http_timeout(timeout)) as client:
                try:
                    r = await post_with_retry(
                        client, url, settings.LLM_MAX_RETRIES, json=payload, headers=self._headers()
                    )
                except httpx.HTTPStatusError as e:
                    if e.response.status_code in (400, 422) and (json_mode or json_schema):
                        # model rejected JSON mode: retry plain; caller still parses robustly
                        payload.pop("nvext", None)
                        payload.pop("response_format", None)
                        r = await post_with_retry(
                            client, url, settings.LLM_MAX_RETRIES, json=payload, headers=self._headers()
                        )
                    else:
                        raise
                content = r.json()["choices"][0]["message"].get("content") or ""
                return _THINK_RE.sub("", content).strip()
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise LLMUnavailableError(f"Cannot reach NVIDIA API at {self.base_url}: {e!r}")
        except httpx.HTTPStatusError as e:
            raise LLMUnavailableError(f"NVIDIA API returned error: {e.response.status_code}")

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: float = 900.0,
        seed: Optional[int] = None,  # accepted for interface parity; not sent
        json_mode: bool = False,
        json_schema: Optional[dict] = None,
        system: Optional[str] = None,
        **_ignored,
    ) -> str:
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        return await self.chat(
            messages, model=model, temperature=temperature, max_tokens=max_tokens,
            timeout=timeout, json_mode=json_mode, json_schema=json_schema,
        )

    async def stream_chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        timeout: float = 300.0,
    ) -> AsyncGenerator[str, None]:
        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=http_timeout(timeout)) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/chat/completions",
                    json=payload, headers=self._headers(),
                ) as r:
                    r.raise_for_status()
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            return
                        try:
                            delta = json.loads(data)["choices"][0].get("delta", {})
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
                        if delta.get("content"):
                            yield delta["content"]
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise LLMUnavailableError(f"Cannot reach NVIDIA API at {self.base_url}: {e!r}")
        except httpx.HTTPStatusError as e:
            raise LLMUnavailableError(f"NVIDIA API returned error: {e.response.status_code}")


class CloudAdapter:
    """The provider chosen on the AI Model tab when it is OpenAI, Anthropic, Grok or a custom OpenAI-compatible service.

    Same methods as the Ollama client. A model name passed by a caller is an Ollama name and is ignored: the model
    comes from the provider's own setting.
    """

    def _target(self):
        provider = settings.LLM_PROVIDER
        problems = cloud_clients.config_problems(provider, "ai")
        if problems:
            raise LLMUnavailableError("; ".join(problems) + " (Settings > AI Model)")
        cfg = cloud_clients.settings_for(provider, "ai")
        return cloud_clients.build_client(provider, cfg["url"], cfg["key"]), cfg["model"]

    async def list_models(self) -> list[str]:
        try:
            client, model = self._target()
            return await client.list_models()
        except Exception:
            return []

    async def chat(self, messages: list[dict], model: Optional[str] = None, temperature: float = 0.1,
                   max_tokens: Optional[int] = None, timeout: float = 120.0, json_mode: bool = False,
                   json_schema: Optional[dict] = None, **_ignored) -> str:
        client, cloud_model = self._target()
        return await client.chat(messages, model=cloud_model, temperature=temperature,
                                 max_tokens=max_tokens or settings.AI_MAX_TOKENS, timeout=timeout,
                                 json_mode=json_mode, json_schema=json_schema)

    async def generate(self, prompt: str, model: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 4096,
                       timeout: float = 900.0, seed: Optional[int] = None, json_mode: bool = False,
                       json_schema: Optional[dict] = None, system: Optional[str] = None, **_ignored) -> str:
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        return await self.chat(messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout,
                               json_mode=json_mode, json_schema=json_schema)

    async def stream_chat(self, messages: list[dict], model: Optional[str] = None, temperature: float = 0.7,
                          timeout: float = 300.0) -> AsyncGenerator[str, None]:
        client, cloud_model = self._target()
        async for piece in client.stream_chat(messages, model=cloud_model, temperature=temperature, timeout=timeout):
            yield piece


class LLMClient:
    """Dispatches to the provider selected by settings.LLM_PROVIDER at call time."""

    def __init__(self):
        self._nvidia = NvidiaClient()
        self._cloud = CloudAdapter()
        self._sem: Optional[asyncio.Semaphore] = None
        self._sem_size = 0

    async def run_limited(self, coro):
        """Await `coro` (a coroutine or a zero-argument factory returning one) under the LLM_CONCURRENCY cap."""
        size = max(1, int(settings.LLM_CONCURRENCY))
        if self._sem is None or size != self._sem_size:   # follows a change on the Settings page
            self._sem, self._sem_size = asyncio.Semaphore(size), size
        async with self._sem:
            return await (coro() if callable(coro) else coro)

    @property
    def provider(self) -> str:
        return settings.LLM_PROVIDER

    @property
    def _active(self):
        if settings.LLM_PROVIDER == "nvidia":
            return self._nvidia
        if settings.LLM_PROVIDER in cloud_clients.CLOUD_PROVIDERS:
            return self._cloud
        return ollama_client

    async def list_models(self) -> list[str]:
        return await self._active.list_models()

    async def generate(self, *args, **kwargs) -> str:
        return await self._active.generate(*args, **kwargs)

    async def chat(self, *args, **kwargs) -> str:
        return await self._active.chat(*args, **kwargs)

    def stream_chat(self, *args, **kwargs) -> AsyncGenerator[str, None]:
        return self._active.stream_chat(*args, **kwargs)

    async def embed(self, *args, **kwargs) -> list[float]:
        # Always local: keeps pgvector embeddings consistent and avoids sending KB text out.
        return await ollama_client.embed(*args, **kwargs)


llm_client = LLMClient()
