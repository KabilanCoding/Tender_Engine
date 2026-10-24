import asyncio
import json
import httpx
from typing import AsyncGenerator, Optional
from app.core.config import settings

EMBED_MODEL = "bge-m3"


class OllamaUnavailableError(Exception):
    pass


_RETRY_STATUS = {429, 500, 502, 503, 504}
CONNECT_TIMEOUT_S = 10.0   # a remote Ollama that does not answer is reported in seconds, not after the full read timeout


def http_timeout(read: float) -> httpx.Timeout:
    """Short connect timeout, long read timeout (model generation on a remote/CPU host is slow)."""
    return httpx.Timeout(read, connect=min(CONNECT_TIMEOUT_S, read))


async def post_with_retry(client: httpx.AsyncClient, url: str, retries: int, **kwargs) -> httpx.Response:
    """POST, retrying transient failures (connect errors/timeouts, 429/5xx) with backoff."""
    delay = 1.0
    for attempt in range(retries + 1):
        try:
            r = await client.post(url, **kwargs)
            if r.status_code in _RETRY_STATUS and attempt < retries:
                await asyncio.sleep(delay)
                delay *= 2
                continue
            r.raise_for_status()
            return r
        except (httpx.ConnectError, httpx.ConnectTimeout):   # not ReadTimeout: that would re-run a slow generation
            if attempt >= retries:
                raise
            await asyncio.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


class OllamaClient:
    # read on every call so a change on the Settings page applies immediately
    @property
    def base_url(self) -> str:
        return settings.OLLAMA_BASE_URL.rstrip("/")

    @property
    def default_model(self) -> str:
        return settings.OLLAMA_MODEL

    def _model(self, requested: Optional[str]) -> str:
        model = requested or self.default_model
        if not model:
            raise OllamaUnavailableError(
                "No AI model is selected. An administrator must choose a default model under Settings > AI Model.")
        return model

    # Known embed-only model name fragments — these cannot generate text
    _EMBED_PATTERNS = ("embed", "minilm", "arctic-embed", "bge-m3")

    def _is_embed_model(self, name: str) -> bool:
        lower = name.lower()
        return any(p in lower for p in self._EMBED_PATTERNS)

    async def list_models(self) -> list[str]:
        """Return names of generative Ollama models (embedding-only models excluded)."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                r.raise_for_status()
                return [
                    m["name"]
                    for m in r.json().get("models", [])
                    if not self._is_embed_model(m["name"])
                ]
        except Exception:
            return []

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: float = 900.0,
        seed: Optional[int] = None,
        json_mode: bool = False,
        json_schema: Optional[dict] = None,
        system: Optional[str] = None,
        num_ctx: Optional[int] = None,
    ) -> str:
        model = self._model(model)
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": self._options(temperature, max_tokens, seed, num_ctx),
            "keep_alive": settings.OLLAMA_KEEP_ALIVE,
        }
        if system:
            payload["system"] = system
        if json_schema or json_mode:
            payload["format"] = json_schema or "json"
        try:
            async with httpx.AsyncClient(timeout=http_timeout(timeout)) as client:
                response = await post_with_retry(
                    client, f"{self.base_url}/api/generate", settings.LLM_MAX_RETRIES, json=payload
                )
                return response.json()["response"]
        except httpx.ConnectError:
            raise OllamaUnavailableError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Ensure Ollama is running and the model is pulled."
            )
        except httpx.ConnectTimeout:
            raise OllamaUnavailableError(
                f"Ollama at {self.base_url} did not answer within {CONNECT_TIMEOUT_S:.0f}s; check the network and the address.")
        except httpx.TimeoutException:
            raise OllamaUnavailableError(f"Ollama timed out after {timeout:.0f}s.")
        except httpx.HTTPStatusError as e:
            raise OllamaUnavailableError(f"Ollama returned error: {e.response.status_code}")

    @staticmethod
    def _options(temperature: float, max_tokens: Optional[int], seed: Optional[int], num_ctx: Optional[int]) -> dict:
        # Ollama silently truncates input beyond num_ctx, so always set it explicitly.
        options: dict = {"temperature": temperature, "num_ctx": num_ctx or settings.OLLAMA_NUM_CTX}
        if max_tokens:
            options["num_predict"] = max_tokens
        if seed is not None:
            options["seed"] = seed
        return options

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        timeout: float = 120.0,
        json_mode: bool = False,
        json_schema: Optional[dict] = None,
        num_ctx: Optional[int] = None,
    ) -> str:
        model = self._model(model)
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": self._options(temperature, max_tokens, None, num_ctx),
            "keep_alive": settings.OLLAMA_KEEP_ALIVE,
        }
        if json_schema or json_mode:
            payload["format"] = json_schema or "json"
        # Streamed so `timeout` limits the silence between tokens, not the whole answer: a slow (CPU / remote)
        # host that is still producing tokens must not be cut off and then asked the same question again.
        delay = 1.0
        for attempt in range(settings.LLM_MAX_RETRIES + 1):
            parts: list[str] = []
            try:
                async with httpx.AsyncClient(timeout=http_timeout(timeout)) as client:
                    async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line.strip():
                                continue
                            try:
                                data = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            if data.get("error"):
                                raise OllamaUnavailableError(f"Ollama error: {data['error']}")
                            parts.append((data.get("message") or {}).get("content", ""))
                            if data.get("done"):
                                break
                return "".join(parts)
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                if attempt < settings.LLM_MAX_RETRIES:
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                if isinstance(e, httpx.ConnectTimeout):
                    raise OllamaUnavailableError(
                        f"Ollama at {self.base_url} did not answer within {CONNECT_TIMEOUT_S:.0f}s; "
                        "check the network and the address.")
                raise OllamaUnavailableError(f"Cannot connect to Ollama at {self.base_url}.")
            except httpx.TimeoutException:
                raise OllamaUnavailableError(f"Ollama sent nothing for {timeout:.0f}s.")
            except httpx.HTTPStatusError as e:
                raise OllamaUnavailableError(f"Ollama returned error: {e.response.status_code}")
        raise OllamaUnavailableError("Ollama chat failed.")

    async def stream_chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        timeout: float = 300.0,
    ) -> AsyncGenerator[str, None]:
        """Yield text chunks from Ollama as they arrive (streaming mode)."""
        model = self._model(model)
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": self._options(temperature, None, None, None),
            "keep_alive": settings.OLLAMA_KEEP_ALIVE,
        }
        try:
            async with httpx.AsyncClient(timeout=http_timeout(timeout)) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/api/chat", json=payload
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            content = data.get("message", {}).get("content", "")
                            if content:
                                yield content
                            if data.get("done"):
                                return
                        except json.JSONDecodeError:
                            continue
        except httpx.ConnectError:
            raise OllamaUnavailableError(
                f"Cannot connect to Ollama at {self.base_url}."
            )

    async def embed(self, text: str, model: Optional[str] = None) -> list[float]:
        """Return the embedding vector of `text` from the model chosen on the Settings page (default bge-m3, 1024 dims)."""
        payload = {"model": model or settings.EMBED_MODEL or EMBED_MODEL, "prompt": text}
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(f"{self.base_url}/api/embeddings", json=payload)
                response.raise_for_status()
                return response.json()["embedding"]
        except httpx.ConnectError:
            raise OllamaUnavailableError(
                f"Cannot connect to Ollama at {self.base_url} for embeddings."
            )
        except httpx.HTTPStatusError as e:
            raise OllamaUnavailableError(f"Ollama embeddings error: {e.response.status_code}")


ollama_client = OllamaClient()
