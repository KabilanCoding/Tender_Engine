"""Per-run LLM options chosen on the Settings page (browser) and sent with each tender analysis."""
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from app.ai import cloud_clients
from app.core.config import settings

MIN_NUM_CTX = 8192        # the extraction prompt plus a 3000-char page needs more than Ollama's small defaults
MAX_NUM_CTX = 131072
MIN_MAX_TOKENS, MAX_MAX_TOKENS = 256, 16384
MAX_INSTRUCTIONS_CHARS = 2000


@dataclass
class RunOptions:
    model: Optional[str] = None          # None = ELIGIBILITY_MODEL from the server, else the provider default
    num_ctx: Optional[int] = None
    max_tokens: Optional[int] = None
    instructions: str = ""               # extra eligibility instructions from Settings > Prompts

    @classmethod
    def build(cls, model: Optional[str] = None, num_ctx: Optional[int] = None,
              max_tokens: Optional[int] = None, instructions: Optional[str] = None) -> "RunOptions":
        """Sanitise untrusted values coming from the browser."""
        model = (model or "").strip()[:200] or None
        if instructions is None:
            instructions = settings.PROMPT_ELIGIBILITY
        if num_ctx:
            # never below the minimum: a smaller window silently truncates the tender text
            num_ctx = max(MIN_NUM_CTX, min(int(num_ctx), MAX_NUM_CTX))
        if max_tokens:
            max_tokens = max(MIN_MAX_TOKENS, min(int(max_tokens), MAX_MAX_TOKENS))
        return cls(model=model, num_ctx=num_ctx or None, max_tokens=max_tokens or None,
                   instructions=(instructions or "").strip()[:MAX_INSTRUCTIONS_CHARS])

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "RunOptions":
        data = data or {}
        return cls.build(data.get("model"), data.get("num_ctx"), data.get("max_tokens"), data.get("instructions"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def primary_model(self) -> Optional[str]:
        """Settings page choice first, then the server-side ELIGIBILITY_MODEL, else the provider default.
        A cloud provider has its own model setting; an Ollama model name sent by the browser does not apply to it."""
        if cloud_clients.is_cloud():
            return cloud_clients.settings_for(cloud_clients.effective_provider())["model"] or None
        return self.model or settings.ELIGIBILITY_MODEL or None

    def resolved_model(self) -> str:
        return self.primary_model or (
            settings.NVIDIA_MODEL if cloud_clients.effective_provider() == "nvidia" else settings.OLLAMA_MODEL)

    def resolved_num_ctx(self) -> int:
        return max(MIN_NUM_CTX, self.num_ctx or settings.OLLAMA_NUM_CTX)

    def source(self) -> str:
        if cloud_clients.is_cloud():
            return f"Settings > Tender Analysis ({cloud_clients.PROVIDER_LABELS[cloud_clients.effective_provider()]})"
        if self.model:
            return "chosen for this run"
        return "Settings > Tender Analysis" if settings.ELIGIBILITY_MODEL else "Settings > AI Model"
