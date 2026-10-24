"""Tolerant JSON recovery for LLM output (code fences, <think> blocks, truncation, single quotes)."""
import ast
import json
import re
from typing import Any, List

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_WRAPPER_KEYS = ("criteria", "items", "results", "reasonings")


def _clean(content: str) -> str:
    text = _THINK_RE.sub("", content).strip()
    text = re.sub(r"```(?:json)?", "", text).strip()
    return text.rstrip("`").strip()


def _unwrap(parsed: Any) -> Any:
    """{"criteria": [...]} -> [...]; leaves any other shape alone."""
    if isinstance(parsed, dict):
        for key in _WRAPPER_KEYS:
            if isinstance(parsed.get(key), list):
                return parsed[key]
    return parsed


def _object_end(text: str, start: int) -> int:
    """Index just past the `}` matching the `{` at `start` (string-aware), or -1 if unterminated."""
    depth, in_str, quote, i = 0, False, "", start
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 1
            elif ch == quote:
                in_str = False
        elif ch in "\"'":
            in_str, quote = True, ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def _salvage_objects(text: str, required_key: str) -> List[dict]:
    """Pull complete {...} objects out of truncated output (skips the unterminated tail)."""
    found: List[dict] = []
    i = 0
    while True:
        i = text.find("{", i)
        if i < 0:
            return found
        end = _object_end(text, i)
        if end < 0:
            i += 1  # unterminated (e.g. the outer wrapper): look for complete objects inside it
            continue
        obj = None
        for loader in (json.loads, ast.literal_eval):
            try:
                obj = loader(text[i:end])
                break
            except Exception:
                continue
        if isinstance(obj, dict) and required_key in obj:
            found.append(obj)
            i = end
        else:
            i += 1


def parse_json_robust(content: str, required_key: str = "source_text") -> Any:
    """Parse model output into JSON; raises ValueError if nothing usable can be recovered.

    `required_key` is only used when salvaging objects from truncated output.
    """
    if not content or not content.strip():
        raise ValueError("Empty LLM content")
    text = _clean(content)

    try:
        return _unwrap(json.loads(text))
    except Exception:
        pass

    match = re.search(r"\{\s*\"(?:%s)\"\s*:\s*\[.*\]\s*\}" % "|".join(_WRAPPER_KEYS), text, re.DOTALL)
    if match:
        try:
            return _unwrap(json.loads(match.group(0)))
        except Exception:
            pass

    match = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
    if match:
        for loader in (json.loads, ast.literal_eval):
            try:
                res = loader(match.group(0))
                if isinstance(res, list):
                    return res
            except Exception:
                continue

    if re.match(r"^\s*\[\s*\]", text):
        return []

    try:
        res = ast.literal_eval(text)
        if isinstance(res, (list, dict)):
            return _unwrap(res)
    except Exception:
        pass

    salvaged = _salvage_objects(text, required_key)
    if salvaged:
        return salvaged

    raise ValueError(f"Truncated or invalid JSON output from LLM: {content[:100]}...")
