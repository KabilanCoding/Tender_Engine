"""Cloud LLM clients for tender analysis: OpenAI-compatible services (OpenAI, Grok/xAI, Groq, Azure, vLLM...) and Anthropic.

Which service tender analysis uses is chosen on Settings > Tender Analysis (tender.provider). Calls here send the
tender text to that service over the internet; the local Ollama path is untouched.
"""
import json
import re
import time
from dataclasses import dataclass
from typing import AsyncGenerator, List, Optional

import httpx

from app.ai.ollama_client import OllamaClient, OllamaUnavailableError, http_timeout
from app.core import settings_registry as registry
from app.core.config import settings

CLOUD_PROVIDERS = ("openai", "anthropic", "grok", "custom")
PROVIDER_LABELS = {"default": "AI Model tab provider", "ollama": "Local Ollama", "openai": "OpenAI",
                   "anthropic": "Anthropic", "grok": "Grok (xAI)", "custom": "Custom OpenAI-compatible", "nvidia": "NVIDIA"}
ANTHROPIC_VERSION = "2023-06-01"


class CloudLLMError(OllamaUnavailableError):
    """The cloud service could not be reached or refused the request. Subclasses the Ollama error so the
    pipeline's existing handlers treat it like any other unavailable-model failure."""


def _error_text(response: httpx.Response) -> str:
    try:
        body = response.json()
        err = body.get("error", body)
        if isinstance(err, dict):
            err = err.get("message") or json.dumps(err)
        return str(err)[:300]
    except Exception:
        return response.text[:300]


def _explain(status: int, detail: str) -> str:
    hint = {401: "the API key is wrong or missing", 403: "the key is not allowed to use this model",
            404: "the address or model name is wrong", 429: "rate limit or quota reached"}.get(status, "")
    return f"HTTP {status}{' (' + hint + ')' if hint else ''}: {detail}"


class OpenAICompatClient:
    """POST {base}/chat/completions, the API OpenAI, xAI and many others share."""

    def __init__(self, base_url: str, api_key: str, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._transport = transport

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def list_models(self) -> List[str]:
        try:
            async with httpx.AsyncClient(timeout=15.0, transport=self._transport) as client:
                r = await client.get(f"{self.base_url}/models", headers=self._headers())
        except httpx.HTTPError as e:
            raise CloudLLMError(f"Cannot reach {self.base_url}: {type(e).__name__}")
        if r.status_code >= 400:
            raise CloudLLMError(_explain(r.status_code, _error_text(r)))
        return sorted({m["id"] for m in r.json().get("data", []) if m.get("id")})

    async def chat(self, messages: list, model: str, temperature: float = 0.0, max_tokens: Optional[int] = 2048,
                   timeout: float = 120.0, json_mode: bool = False, json_schema: Optional[dict] = None) -> str:
        wants_json = bool(json_mode or json_schema)
        msgs = [dict(m) for m in messages]
        if wants_json and msgs and msgs[0]["role"] == "system":
            msgs[0]["content"] += "\n\nRespond with a single valid JSON object only."   # json_object mode requires the word JSON
        payload = {"model": model, "messages": msgs, "stream": False, "temperature": temperature}
        # OpenAI's newer models want max_completion_tokens; other services still expect max_tokens
        token_key = "max_completion_tokens" if "api.openai.com" in self.base_url else "max_tokens"
        if max_tokens:
            payload[token_key] = max_tokens
        if json_schema:
            payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "result", "schema": json_schema}}
        elif json_mode:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=http_timeout(timeout), transport=self._transport) as client:
            for _ in range(5):          # a service may reject one parameter at a time; adapt and retry
                try:
                    r = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=self._headers())
                except httpx.TimeoutException:
                    raise CloudLLMError(f"{self.base_url} did not answer within {timeout:.0f}s")
                except httpx.HTTPError as e:
                    raise CloudLLMError(f"Cannot reach {self.base_url}: {type(e).__name__}")
                if r.status_code < 400:
                    return self._text(r)
                detail = _error_text(r)
                if r.status_code == 400 and self._adapt(payload, detail.lower()):
                    continue
                raise CloudLLMError(_explain(r.status_code, detail))
        raise CloudLLMError("The service kept rejecting the request parameters")

    async def stream_chat(self, messages: list, model: str, temperature: float = 0.7, timeout: float = 300.0) -> AsyncGenerator[str, None]:
        payload = {"model": model, "messages": messages, "temperature": temperature, "stream": True}
        async with httpx.AsyncClient(timeout=http_timeout(timeout), transport=self._transport) as client:
            try:
                async with client.stream("POST", f"{self.base_url}/chat/completions", json=payload, headers=self._headers()) as r:
                    if r.status_code >= 400:
                        await r.aread()
                        raise CloudLLMError(_explain(r.status_code, _error_text(r)))
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
            except httpx.TimeoutException:
                raise CloudLLMError(f"{self.base_url} did not answer within {timeout:.0f}s")
            except httpx.HTTPError as e:
                raise CloudLLMError(f"Cannot reach {self.base_url}: {type(e).__name__}")

    @staticmethod
    def _adapt(payload: dict, low: str) -> bool:
        """Drop or rename the parameter the service complained about. False when nothing can be changed."""
        if "max_completion_tokens" in payload and "max_completion_tokens" in low:
            payload["max_tokens"] = payload.pop("max_completion_tokens")
            return True
        if "max_tokens" in payload and "max_completion_tokens" in low:
            payload["max_completion_tokens"] = payload.pop("max_tokens")
            return True
        if "temperature" in payload and "temperature" in low:
            payload.pop("temperature")
            return True
        rf = payload.get("response_format")
        if rf and ("response_format" in low or "schema" in low or "json" in low):
            if rf.get("type") == "json_schema":
                payload["response_format"] = {"type": "json_object"}
            else:
                payload.pop("response_format")
            return True
        return False

    @staticmethod
    def _text(r: httpx.Response) -> str:
        try:
            content = r.json()["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, ValueError):
            raise CloudLLMError("The service answered in an unexpected format")
        if isinstance(content, list):        # some services return content parts
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()


class AnthropicClient:
    """POST {base}/messages, Anthropic's own API."""

    def __init__(self, base_url: str, api_key: str, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._transport = transport

    def _headers(self) -> dict:
        return {"x-api-key": self.api_key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}

    async def list_models(self) -> List[str]:
        try:
            async with httpx.AsyncClient(timeout=15.0, transport=self._transport) as client:
                r = await client.get(f"{self.base_url}/models", params={"limit": 100}, headers=self._headers())
        except httpx.HTTPError as e:
            raise CloudLLMError(f"Cannot reach {self.base_url}: {type(e).__name__}")
        if r.status_code >= 400:
            raise CloudLLMError(_explain(r.status_code, _error_text(r)))
        return [m["id"] for m in r.json().get("data", []) if m.get("id")]

    async def chat(self, messages: list, model: str, temperature: float = 0.0, max_tokens: Optional[int] = 2048,
                   timeout: float = 120.0, json_mode: bool = False, json_schema: Optional[dict] = None) -> str:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        if json_mode or json_schema:
            system += "\n\nRespond with a single valid JSON value only: no prose and no code fences."
            if json_schema:
                system += f"\nThe JSON must follow this JSON Schema:\n{json.dumps(json_schema)}"
        payload = {"model": model, "max_tokens": max_tokens or 2048, "temperature": temperature,
                   "messages": [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]}
        if system.strip():
            payload["system"] = system.strip()
        async with httpx.AsyncClient(timeout=http_timeout(timeout), transport=self._transport) as client:
            for _ in range(2):
                try:
                    r = await client.post(f"{self.base_url}/messages", json=payload, headers=self._headers())
                except httpx.TimeoutException:
                    raise CloudLLMError(f"{self.base_url} did not answer within {timeout:.0f}s")
                except httpx.HTTPError as e:
                    raise CloudLLMError(f"Cannot reach {self.base_url}: {type(e).__name__}")
                if r.status_code < 400:
                    break
                detail = _error_text(r)
                if r.status_code == 400 and "temperature" in payload and "temperature" in detail.lower():
                    payload.pop("temperature")      # some newer models fix the temperature themselves
                    continue
                raise CloudLLMError(_explain(r.status_code, detail))
            else:
                raise CloudLLMError("The service kept rejecting the request parameters")
        try:
            blocks = r.json()["content"]
        except (KeyError, ValueError):
            raise CloudLLMError("The service answered in an unexpected format")
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()


    async def stream_chat(self, messages: list, model: str, temperature: float = 0.7, timeout: float = 300.0) -> AsyncGenerator[str, None]:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        payload = {"model": model, "max_tokens": 4096, "temperature": temperature, "stream": True,
                   "messages": [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]}
        if system.strip():
            payload["system"] = system.strip()
        async with httpx.AsyncClient(timeout=http_timeout(timeout), transport=self._transport) as client:
            try:
                async with client.stream("POST", f"{self.base_url}/messages", json=payload, headers=self._headers()) as r:
                    if r.status_code >= 400:
                        await r.aread()
                        raise CloudLLMError(_explain(r.status_code, _error_text(r)))
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        try:
                            event = json.loads(line[5:].strip())
                        except json.JSONDecodeError:
                            continue
                        if event.get("type") == "content_block_delta" and event.get("delta", {}).get("text"):
                            yield event["delta"]["text"]
                        elif event.get("type") == "message_stop":
                            return
            except httpx.TimeoutException:
                raise CloudLLMError(f"{self.base_url} did not answer within {timeout:.0f}s")
            except httpx.HTTPError as e:
                raise CloudLLMError(f"Cannot reach {self.base_url}: {type(e).__name__}")


# ---------------------------------------------------------------------------
# Which service tender analysis should use right now
# ---------------------------------------------------------------------------

def effective_provider() -> str:
    """ollama | nvidia | openai | anthropic | grok | custom: what tender analysis really talks to."""
    chosen = settings.TENDER_PROVIDER
    return settings.LLM_PROVIDER if chosen == "default" else chosen


def is_cloud() -> bool:
    return effective_provider() in CLOUD_PROVIDERS


@dataclass
class CloudTarget:
    provider: str
    client: object
    model: str
    base_url: str


def setting_keys(scope: str, provider: str) -> dict:
    """Registry keys that hold the address, API key and model of a provider on the AI Model tab ('ai') or Tender Analysis tab ('tender')."""
    if scope == "ai" and provider == "nvidia":
        return {"url": "ai.nvidia_base_url", "key": "ai.nvidia_key", "model": "ai.nvidia_model"}
    return {f: f"{scope}.{provider}_{f}" for f in ("url", "key", "model")}


def settings_for(provider: str, scope: Optional[str] = None) -> dict:
    """Current {url, key, model} of a provider. Tender analysis uses its own entries when it has its own provider,
    and the AI Model tab's entries when it follows that tab."""
    scope = scope or ("ai" if settings.TENDER_PROVIDER == "default" else "tender")
    out = {f: getattr(settings, registry.BY_KEY[k].attr) for f, k in setting_keys(scope, provider).items()}
    if provider == "nvidia" and not out["key"]:
        out["key"] = settings.NVIDIA_API_KEY            # the server env file still works
    return out


def build_client(provider: str, url: str, key: str, transport=None):
    return (AnthropicClient if provider == "anthropic" else OpenAICompatClient)(url, key, transport=transport)


def problems_with(provider: str, url: str, key: str, model: str) -> List[str]:
    out = []
    if not url.startswith(("http://", "https://")):
        out.append(f"{PROVIDER_LABELS[provider]}: the address must start with http:// or https://")
    if not key:
        out.append(f"{PROVIDER_LABELS[provider]}: no API key is saved")
    if not model:
        out.append(f"{PROVIDER_LABELS[provider]}: no model is chosen")
    return out


def config_problems(provider: str, scope: str = "ai") -> List[str]:
    """What is missing for a cloud or NVIDIA provider (empty list = ready to use)."""
    cfg = settings_for(provider, scope)
    return problems_with(provider, cfg["url"], cfg["key"], cfg["model"])


def cloud_target() -> Optional[CloudTarget]:
    """The cloud service chosen for tender analysis, or None when it runs on Ollama/NVIDIA. Raises when misconfigured."""
    provider = effective_provider()
    if provider not in CLOUD_PROVIDERS:
        return None
    cfg = settings_for(provider)
    problems = problems_with(provider, cfg["url"], cfg["key"], cfg["model"])
    if problems:
        raise CloudLLMError("; ".join(problems) + " (on the Settings page)")
    return CloudTarget(provider, build_client(provider, cfg["url"], cfg["key"]), cfg["model"], cfg["url"])


class _OllamaAt(OllamaClient):
    def __init__(self, url: str):
        self._url = url

    @property
    def base_url(self) -> str:
        return self._url.rstrip("/")


def tender_ollama_client() -> Optional[OllamaClient]:
    """A local-Ollama client for tender analysis when it must differ from the global one, else None (use the shared client)."""
    if settings.TENDER_PROVIDER == "ollama" and settings.TENDER_OLLAMA_URL:
        return _OllamaAt(settings.TENDER_OLLAMA_URL)
    return None


async def ping(provider: str, url: str, key: str, model: str) -> dict:
    """Send one tiny request to check address, key and model. Never raises; returns {ok, ms, reply|error}."""
    started = time.monotonic()
    try:
        if provider == "ollama":
            from app.ai.ollama_client import ollama_client
            models = await (_OllamaAt(url) if url else ollama_client).list_models()
            if not models:
                raise CloudLLMError("Ollama is not reachable or has no models installed")
            return {"ok": True, "ms": int((time.monotonic() - started) * 1000), "reply": f"{len(models)} models installed"}
        problems = problems_with(provider, url, key, model)
        if problems:
            return {"ok": False, "error": "; ".join(problems)}
        reply = await build_client(provider, url, key).chat(
            [{"role": "user", "content": "Reply with the single word OK."}],
            model=model, temperature=0.0, max_tokens=64, timeout=30.0)
        return {"ok": True, "ms": int((time.monotonic() - started) * 1000),
                "reply": reply[:80] or "(empty reply, but the service accepted the request)"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:400]}
