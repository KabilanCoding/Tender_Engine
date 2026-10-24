"""Definitions of every setting that can be changed from the Settings page.

Only things the server needs *before* it can reach the database stay in the env file
(DATABASE_URL, SECRET_KEY, ENVIRONMENT, UPLOAD_DIR, CORS_ORIGINS, NVIDIA_API_KEY). Everything else is here.

`attr` is the attribute name code reads from `app.core.config.settings`, e.g. settings.OLLAMA_MODEL.
This module has no imports from the app so it can be loaded anywhere.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class SettingDef:
    key: str                      # stable id used by the API, e.g. "ai.default_model"
    attr: str                     # attribute on `settings`
    group: str                    # ai | search | prompts | tender | system
    type: str                     # int | float | bool | str | text | choice | secret (API key: stored encrypted, never sent back)
    default: Any
    label: str
    help: str = ""
    min: Optional[float] = None
    max: Optional[float] = None
    choices: Tuple[str, ...] = ()
    public: bool = False          # visible to every logged-in role via /settings/effective
    advanced: bool = False        # shown under "Advanced" in the UI


def _d(*args, **kw) -> SettingDef:
    return SettingDef(*args, **kw)


REGISTRY: List[SettingDef] = [
    # ------------------------------------------------------------------ AI
    _d("ai.provider", "LLM_PROVIDER", "ai", "choice", "ollama", "AI provider",
       "ollama runs models on this server. The others send text to that company's cloud API (needs an API key and internet access).",
       choices=("ollama", "nvidia", "openai", "anthropic", "grok", "custom"), public=True),
    _d("ai.ollama_url", "OLLAMA_BASE_URL", "ai", "str", "http://localhost:11434", "Ollama address",
       "Where the Ollama service listens.", advanced=True),
    _d("ai.default_model", "OLLAMA_MODEL", "ai", "str", "", "Default model",
       "Model used for AI features. Pick from the installed models on the AI Model tab.", public=True),
    _d("ai.embed_model", "EMBED_MODEL", "ai", "str", "bge-m3", "Embedding model",
       "Used to index and search the company knowledge base. After changing it, press 'Refresh search index' on the Knowledge Base page "
       "(vectors from different models cannot be compared). Needs the model on the Ollama server, e.g. bge-m3.", advanced=True),
    _d("ai.temperature", "AI_TEMPERATURE", "ai", "float", 0.7, "Temperature",
       "0 = most repeatable, 1 = most varied. Tender analysis always runs at 0.", min=0, max=1, public=True),
    _d("ai.deterministic", "AI_DETERMINISTIC", "ai", "bool", False, "Deterministic mode",
       "Force temperature 0 and a fixed seed for repeatable output.", public=True),
    _d("ai.seed", "AI_SEED", "ai", "int", 42, "Seed", "Used only in deterministic mode.", min=0, max=2147483647, public=True),
    _d("ai.num_ctx", "OLLAMA_NUM_CTX", "ai", "int", 8192, "Context window (tokens)",
       "How much text the model reads at once. Larger = slower. Tender analysis uses at least 8192.",
       min=2048, max=131072, public=True),
    _d("ai.max_tokens", "AI_MAX_TOKENS", "ai", "int", 4096, "Max output tokens", "Longest answer the model may write.",
       min=256, max=16384, public=True),
    _d("ai.keep_alive", "OLLAMA_KEEP_ALIVE", "ai", "str", "30m", "Keep model loaded",
       "How long Ollama keeps the model in memory between requests (e.g. 30m, 2h).", advanced=True),
    _d("ai.max_retries", "LLM_MAX_RETRIES", "ai", "int", 2, "Retries on temporary errors",
       "Connection errors, timeouts and 429/5xx responses are retried this many times.", min=0, max=10, advanced=True),
    _d("ai.concurrency", "LLM_CONCURRENCY", "ai", "int", 1, "Parallel AI calls",
       "How many model calls run at once during tender analysis. Keep 1-2 unless the server has spare GPU memory.",
       min=1, max=16, advanced=True),
    _d("ai.openai_url", "AI_OPENAI_URL", "ai", "str", "https://api.openai.com/v1", "OpenAI address", ""),
    _d("ai.openai_key", "AI_OPENAI_KEY", "ai", "secret", "", "OpenAI API key", ""),
    _d("ai.openai_model", "AI_OPENAI_MODEL", "ai", "str", "gpt-4o-mini", "OpenAI model", ""),
    _d("ai.anthropic_url", "AI_ANTHROPIC_URL", "ai", "str", "https://api.anthropic.com/v1", "Anthropic address", ""),
    _d("ai.anthropic_key", "AI_ANTHROPIC_KEY", "ai", "secret", "", "Anthropic API key", ""),
    _d("ai.anthropic_model", "AI_ANTHROPIC_MODEL", "ai", "str", "claude-sonnet-5-5", "Anthropic model", ""),
    _d("ai.grok_url", "AI_GROK_URL", "ai", "str", "https://api.x.ai/v1", "Grok (xAI) address", ""),
    _d("ai.grok_key", "AI_GROK_KEY", "ai", "secret", "", "Grok (xAI) API key", ""),
    _d("ai.grok_model", "AI_GROK_MODEL", "ai", "str", "grok-4", "Grok (xAI) model", ""),
    _d("ai.custom_url", "AI_CUSTOM_URL", "ai", "str", "", "Custom service address", "Any service that speaks the OpenAI chat API (Groq, Together, Azure OpenAI, LM Studio, vLLM...)."),
    _d("ai.custom_key", "AI_CUSTOM_KEY", "ai", "secret", "", "Custom service API key", ""),
    _d("ai.custom_model", "AI_CUSTOM_MODEL", "ai", "str", "", "Custom service model", ""),
    _d("ai.nvidia_key", "NVIDIA_KEY", "ai", "secret", "", "NVIDIA API key",
       "Saved here, or set NVIDIA_API_KEY in the server's env file."),
    _d("ai.nvidia_base_url", "NVIDIA_BASE_URL", "ai", "str", "https://integrate.api.nvidia.com/v1", "NVIDIA API address",
       "Only used when the provider is nvidia.", advanced=True),
    _d("ai.nvidia_model", "NVIDIA_MODEL", "ai", "str", "meta/llama-3.2-11b-vision-instruct", "NVIDIA model",
       "Only used when the provider is nvidia.", advanced=True),
    _d("ai.nvidia_fallback_model", "NVIDIA_FALLBACK_MODEL", "ai", "str", "nvidia/nemotron-3-super-120b-a12b",
       "NVIDIA fallback model", "Tried when the first attempt fails (nvidia provider only).", advanced=True),

    # ------------------------------------------------------------------ search
    _d("search.top_k", "SEARCH_TOP_K", "search", "int", 8, "Results to retrieve", "Document passages returned per search.",
       min=1, max=50, public=True),
    _d("search.similarity_threshold", "SEARCH_SIMILARITY", "search", "float", 0.0, "Minimum similarity",
       "Hide passages less similar than this (0 = no filtering).", min=0, max=1, public=True),

    # ------------------------------------------------------------------ prompts
    _d("prompts.kb_summary", "PROMPT_KB_SUMMARY", "prompts", "text", "", "Knowledge-base summary prompt",
       "System prompt used when summarising search results. Blank = built-in prompt.", public=True),
    _d("prompts.feature_gen", "PROMPT_FEATURE_GEN", "prompts", "text", "", "Estimation instructions",
       "Extra instructions appended when generating features for an estimate.", public=True),
    _d("prompts.eligibility", "PROMPT_ELIGIBILITY", "prompts", "text", "", "Eligibility instructions",
       "Extra instructions added to tender analysis. The built-in rules and JSON format still apply.", public=True),

    # ------------------------------------------------------------------ tender analysis
    _d("tender.provider", "TENDER_PROVIDER", "tender", "choice", "default", "AI service for tender analysis",
       "default = the provider chosen on the AI Model tab. ollama runs on a local server; openai, anthropic, grok and custom "
       "send the tender text to that company's cloud API (needs an API key and internet access).",
       choices=("default", "ollama", "openai", "anthropic", "grok", "custom")),
    _d("tender.ollama_url", "TENDER_OLLAMA_URL", "tender", "str", "", "Ollama address for tender analysis",
       "Blank = the address on the AI Model tab. The model is chosen in 'Tender analysis model' below."),
    _d("tender.openai_url", "TENDER_OPENAI_URL", "tender", "str", "https://api.openai.com/v1", "OpenAI address", ""),
    _d("tender.openai_key", "TENDER_OPENAI_KEY", "tender", "secret", "", "OpenAI API key", ""),
    _d("tender.openai_model", "TENDER_OPENAI_MODEL", "tender", "str", "gpt-4o-mini", "OpenAI model", ""),
    _d("tender.anthropic_url", "TENDER_ANTHROPIC_URL", "tender", "str", "https://api.anthropic.com/v1", "Anthropic address", ""),
    _d("tender.anthropic_key", "TENDER_ANTHROPIC_KEY", "tender", "secret", "", "Anthropic API key", ""),
    _d("tender.anthropic_model", "TENDER_ANTHROPIC_MODEL", "tender", "str", "claude-sonnet-5-5", "Anthropic model", ""),
    _d("tender.grok_url", "TENDER_GROK_URL", "tender", "str", "https://api.x.ai/v1", "Grok (xAI) address", ""),
    _d("tender.grok_key", "TENDER_GROK_KEY", "tender", "secret", "", "Grok (xAI) API key", ""),
    _d("tender.grok_model", "TENDER_GROK_MODEL", "tender", "str", "grok-4", "Grok (xAI) model", ""),
    _d("tender.custom_url", "TENDER_CUSTOM_URL", "tender", "str", "", "Custom service address",
       "Any service that speaks the OpenAI chat API (Groq, Together, Azure OpenAI, LM Studio, vLLM...)."),
    _d("tender.custom_key", "TENDER_CUSTOM_KEY", "tender", "secret", "", "Custom service API key", ""),
    _d("tender.custom_model", "TENDER_CUSTOM_MODEL", "tender", "str", "", "Custom service model", ""),
    _d("tender.model", "ELIGIBILITY_MODEL", "tender", "str", "", "Tender analysis model",
       "Blank = use the default model. Larger models invent fewer criteria (qwen2.5:14b worked well in testing).", public=True),
    _d("tender.fallback_model", "ELIGIBILITY_FALLBACK_MODEL", "tender", "str", "", "Fallback model",
       "Used from the second attempt on a page. Blank = same model.", advanced=True),
    _d("tender.max_attempts", "ELIGIBILITY_MAX_ATTEMPTS", "tender", "int", 3, "Attempts per page",
       "Covers malformed answers as well as connection errors.", min=1, max=6, advanced=True),
    _d("tender.chunk_timeout_s", "ELIGIBILITY_CHUNK_TIMEOUT_S", "tender", "int", 180, "Timeout per AI call (s)",
       "Local CPU or small-GPU inference is slow; raise this if calls time out.", min=30, max=1800, advanced=True),
    _d("tender.max_tokens", "ELIGIBILITY_MAX_TOKENS", "tender", "int", 4096, "Max output tokens per call",
       min=256, max=16384, advanced=True),
    _d("tender.reasoning_batch", "ELIGIBILITY_REASONING_BATCH", "tender", "int", 5, "Explanations per AI call",
       min=1, max=20, advanced=True),
    _d("tender.reasoning_max_items", "ELIGIBILITY_REASONING_MAX_ITEMS", "tender", "int", 40, "Max AI explanations",
       "Only unresolved criteria get AI-written explanations, up to this many.", min=0, max=500),
    _d("tender.prefilter", "ELIGIBILITY_PREFILTER", "tender", "bool", True, "Skip non-eligibility pages",
       "On large tenders send only pages that look like eligibility text to the AI (much faster)."),
    _d("tender.prefilter_min_chunks", "ELIGIBILITY_PREFILTER_MIN_CHUNKS", "tender", "int", 8, "Filter only tenders longer than (pages)",
       "Shorter tenders are always analysed in full.", min=1, max=500, advanced=True),
    _d("tender.extra_pages", "ELIGIBILITY_EXTRA_PAGES", "tender", "int", 3, "Extra pages outside the eligibility section",
       "When the tender has a clear eligibility section only it is read; this many further pages that look strongly "
       "like eligibility text (blacklisting, DSC, EMD) are added. 0 = eligibility section only (fastest).",
       min=0, max=30),
    _d("tender.prefilter_max_fraction", "ELIGIBILITY_PREFILTER_MAX_FRACTION", "tender", "float", 0.4, "Share of pages sent",
       "Soft cap on the fraction of pages sent to the AI.", min=0.1, max=1, advanced=True),
    _d("tender.grounding_threshold", "GROUNDING_FUZZY_THRESHOLD", "tender", "int", 92, "Quote match threshold (%)",
       "How closely an extracted quote must match the tender text to count as verified.", min=50, max=100),
    _d("tender.grounding_near_miss", "GROUNDING_NEAR_MISS_MIN", "tender", "int", 80, "Near-miss logging threshold (%)",
       "Quotes between this and the threshold are logged for tuning.", min=0, max=100, advanced=True),
    _d("tender.grounding_ocr_threshold", "GROUNDING_OCR_THRESHOLD", "tender", "int", 75, "Quote threshold for scanned pages (%)",
       "Relaxed threshold for OCR text, which contains recognition errors.", min=0, max=100, advanced=True),
    _d("tender.ocr_languages", "OCR_LANGUAGES", "tender", "str", "eng", "OCR languages",
       "Tesseract language codes joined by +, for scanned pages: eng and the Indian languages hin, tam, tel, kan, mal, ben, mar, "
       "guj, pan, ori, asm, nep, san, urd. Only installed packs are used; e.g. eng+tam for an English and Tamil tender."),
    _d("tender.ocr_auto_script", "OCR_AUTO_SCRIPT", "tender", "bool", True, "Detect the script of each scanned page",
       "Look at every scanned page, find its script (Tamil, Devanagari...) and read it with that language pack as well; when a page reads badly, the other installed Indian languages are tried. "
       "A pack that is not installed is reported on the run instead of silently producing garbage."),
    _d("tender.ocr_tessdata_dir", "OCR_TESSDATA_DIR", "tender", "str", "", "Extra OCR language folder",
       "Folder holding additional Tesseract language packs (*.traineddata) when they are not in the system folder. "
       "Empty = the system folder.", advanced=True),
    _d("tender.gate_enabled", "TENDER_GATE_ENABLED", "tender", "bool", True, "Reject non-tender documents",
       "Refuse uploads that do not look like a tender."),
    _d("tender.run_ttl_min", "ELIGIBILITY_RUN_TTL_MIN", "tender", "int", 120, "Stale run timeout (min)",
       "A run still 'running' after this long may be restarted.", min=5, max=1440, advanced=True),

    _d("tender.full_checklist", "FULL_CHECKLIST", "tender", "bool", True, "Full tender checklist",
       "After the eligibility check, also read the whole tender and list its eligibility, scope of work, deliverables, dates, money terms, "
       "submission rules and evaluation rules for a person to compare by hand. Adds several minutes per tender."),
    _d("tender.checklist_model", "CHECKLIST_MODEL", "tender", "str", "", "Full checklist: model",
       "Leave empty to use the same model as the rest of the analysis. A smaller, faster model (for example llama3.1:8b) makes the full "
       "checklist much quicker, at some cost in completeness. The eligibility check always uses the main model.", advanced=True),
    _d("tender.checklist_window_chars", "CHECKLIST_WINDOW_CHARS", "tender", "int", 5500, "Full checklist: text per AI call (characters)",
       "Larger = fewer calls but the model may skip lines. Smaller = slower but more complete.", min=3000, max=16000, advanced=True),
    _d("tender.trace_runs", "TRACE_RUNS", "tender", "bool", False, "Save a step-by-step trace of every analysis (temporary)",
       "For checking by hand: writes the text read from each page, the chunks, what the AI was asked and answered, and the checklist to "
       "uploads/trace/. Turn it off when you are done; it is not needed for normal use.", advanced=True),
    _d("tender.auto_analyse", "AUTO_ANALYSE", "tender", "bool", False, "Analyse new Tender Tiger tenders automatically",
       "n8n sends the tenders it downloaded (POST /api/v1/tender-tiger/auto-analyse); ZYNEX picks each tender's documents "
       "(RFP / NIT, eligibility, scope, corrigenda), analyses them one at a time and posts the result to Teams."),
    _d("tender.auto_timeout_min", "AUTO_TIMEOUT_MIN", "tender", "int", 15, "Automatic analysis: time limit per tender (min)",
       "A tender still running after this is stopped and reported to Teams; 'Analyse again' runs it without a limit.",
       min=3, max=240),
    _d("tender.auto_skip_closed", "AUTO_SKIP_CLOSED", "tender", "bool", True, "Automatic analysis: skip closed tenders",
       "Tenders whose due date has passed are not analysed."),
    _d("tender.auto_queue_max", "AUTO_QUEUE_MAX", "tender", "int", 200, "Automatic analysis: most tenders waiting",
       "New tenders beyond this are not queued (protects against a bad download run).", min=1, max=5000, advanced=True),
    _d("tender.teams_webhook", "TEAMS_WEBHOOK_URL", "tender", "secret", "", "Microsoft Teams webhook",
       "Teams Workflows webhook URL; each analysed tender is posted there as {\"html\": ...}, like the n8n summary. Stored encrypted."),
    _d("tender.public_url", "ZYNEX_PUBLIC_URL", "tender", "str", "", "ZYNEX address for links",
       "Address people open ZYNEX at, e.g. http://10.10.10.19:3000; used for the 'Open in ZYNEX' link on Teams cards."),
    _d("tender.isolate_heavy", "ISOLATE_HEAVY_STAGES", "tender", "bool", True, "Isolate heavy document steps",
       "Read large documents in a separate process so the app stays responsive. Small documents are not affected.", advanced=True),
    _d("tender.stage_timeout_s", "STAGE_TIMEOUT_S", "tender", "int", 900, "Time limit per heavy step (s)",
       "A document step that runs longer than this is stopped and the analysis fails with a clear message.", min=60, max=7200, advanced=True),
    _d("tender.kb_semantic", "KB_SEMANTIC_MATCH", "tender", "bool", True, "Match experience by meaning",
       "Also match past projects to the work a tender asks for by meaning (needs the knowledge-base index). A match found this way "
       "is shown as 'check by hand', never as a pass."),
    _d("tender.kb_semantic_min", "KB_SEMANTIC_MIN_SCORE", "tender", "float", 0.40, "Meaning match: minimum score",
       "Higher = stricter. Rows scoring below this are not offered (score = meaning 65% + shared keywords 35%).", min=0.1, max=0.95, advanced=True),
    _d("tender.kb_rerank", "KB_SEMANTIC_RERANK", "tender", "bool", True, "Double-check meaning matches with the AI",
       "The model re-reads the best few matches and drops the ones that do not fit the requirement. If it fails, the matches are kept as found.",
       advanced=True),

    # ------------------------------------------------------------------ system
    _d("system.max_upload_mb", "MAX_UPLOAD_SIZE_MB", "system", "int", 100, "Max upload size (MB)", min=1, max=2000, public=True),
    _d("system.access_token_minutes", "ACCESS_TOKEN_EXPIRE_MINUTES", "system", "int", 480, "Login session length (min)",
       "Applies to logins made after the change.", min=5, max=10080),
    _d("system.storage_location", "STORAGE_LOCATION", "system", "choice", "local", "Document storage",
       "Where uploaded and generated documents are kept (knowledge-base files, portfolio documents, tenders, proposals). "
       "local = the uploads folder of this machine. file server = the folder below on another server, over SSH. "
       "New files go to the chosen place; older ones are copied to the file server on the next ./run (scripts.move_documents).",
       choices=("local", "file server")),
    _d("system.storage_host", "STORAGE_HOST", "system", "str", "", "File server address",
       "Name or IP address of the file server, e.g. 10.10.10.19."),
    _d("system.storage_user", "STORAGE_USER", "system", "str", "", "File server user", "SSH user that owns the folder."),
    _d("system.storage_password", "STORAGE_PASSWORD", "system", "secret", "", "File server password",
       "Stored encrypted. Leave empty when a key file is used."),
    _d("system.storage_server_dir", "STORAGE_SERVER_DIR", "system", "str", "Tendo_Docs/ZYNEX", "Folder on the file server",
       "Absolute (/home/xenovex/Tendo_Docs/ZYNEX) or relative to the user's home folder. Created when missing."),
    _d("system.storage_port", "STORAGE_PORT", "system", "int", 22, "File server SSH port", min=1, max=65535, advanced=True),
    _d("system.storage_key_file", "STORAGE_KEY_FILE", "system", "str", "", "SSH key file",
       "Private key on this machine to log in with instead of a password, e.g. /home/xenovex/.ssh/id_ed25519.", advanced=True),
]

BY_KEY: Dict[str, SettingDef] = {d.key: d for d in REGISTRY}
BY_ATTR: Dict[str, SettingDef] = {d.attr: d for d in REGISTRY}
GROUPS = ("ai", "search", "prompts", "tender", "system")


class SettingValidationError(ValueError):
    pass


def coerce(defn: SettingDef, raw: Any) -> Any:
    """Validate and convert a value coming from the API; raises SettingValidationError."""
    try:
        if defn.type == "bool":
            if isinstance(raw, bool):
                value = raw
            elif str(raw).lower() in ("true", "1", "yes", "on"):
                value = True
            elif str(raw).lower() in ("false", "0", "no", "off"):
                value = False
            else:
                raise ValueError("expected true or false")
        elif defn.type == "int":
            if isinstance(raw, bool) or (isinstance(raw, float) and raw != int(raw)):
                raise ValueError("expected a whole number")
            value = int(raw)
        elif defn.type == "float":
            if isinstance(raw, bool):
                raise ValueError("expected a number")
            value = float(raw)
        else:  # str | text | choice | secret
            if not isinstance(raw, str):
                raise ValueError("expected text")
            value = raw.strip() if defn.type != "text" else raw
    except (TypeError, ValueError) as e:
        raise SettingValidationError(f"{defn.label}: {e}")

    if defn.type in ("int", "float"):
        if defn.min is not None and value < defn.min:
            raise SettingValidationError(f"{defn.label}: must be at least {defn.min:g}")
        if defn.max is not None and value > defn.max:
            raise SettingValidationError(f"{defn.label}: must be at most {defn.max:g}")
    if defn.type == "choice" and value not in defn.choices:
        raise SettingValidationError(f"{defn.label}: must be one of {', '.join(defn.choices)}")
    if defn.type == "text" and len(value) > 4000:
        raise SettingValidationError(f"{defn.label}: at most 4000 characters")
    if defn.type in ("str", "secret") and len(value) > 500:
        raise SettingValidationError(f"{defn.label}: at most 500 characters")
    return value
