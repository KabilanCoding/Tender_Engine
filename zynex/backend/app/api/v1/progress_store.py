"""
In-memory progress store for long-running AI jobs.
Keys can be int (project_id for generate) or str (e.g. "chat_42" for advisor).
"""
from datetime import datetime
from typing import Union

Key = Union[int, str]
_store: dict[Key, list[dict]] = {}


def init(key: Key) -> None:
    _store[key] = []
    _stage.pop(key, None)
    _metrics.pop(key, None)


def push(key: Key, message: str, level: str = "info") -> None:
    """level: 'info' | 'working' | 'success' | 'error'"""
    if key not in _store:
        _store[key] = []
    _store[key].append({
        "message": message,
        "level": level,
        "ts": datetime.now().strftime("%H:%M:%S"),
    })


def get(key: Key) -> list[dict]:
    return list(_store.get(key, []))


def clear(key: Key) -> None:
    _store.pop(key, None)
    _stage.pop(key, None)
    _metrics.pop(key, None)


# ---- stage + live metrics (used by the tender screens) --------------------
_stage: dict[Key, str] = {}
_metrics: dict[Key, dict] = {}


def set_stage(key: Key, stage: str) -> None:
    _stage[key] = stage


def get_stage(key: Key) -> str | None:
    return _stage.get(key)


def update_metrics(key: Key, **values) -> None:
    _metrics.setdefault(key, {}).update(values)


def get_metrics(key: Key) -> dict:
    return dict(_metrics.get(key, {}))
