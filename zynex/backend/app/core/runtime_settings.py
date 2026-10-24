"""Load, validate and save the settings managed on the Settings page (table app_settings)."""
import asyncio
import logging
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import secret_store
from app.core import settings_registry as registry
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.app_setting import AppSetting

logger = logging.getLogger(__name__)
REFRESH_SECONDS = 15   # lets every worker process pick up a change made through another one


async def load_saved(db: AsyncSession) -> Dict[str, Any]:
    rows = (await db.execute(select(AppSetting))).scalars().all()
    values = {}
    for r in rows:
        defn = registry.BY_KEY.get(r.key)
        if defn is not None:
            values[r.key] = secret_store.decrypt(r.value) if defn.type == "secret" else r.value
    settings.apply_saved(values)
    return values


async def refresh_forever() -> None:
    """Background task: re-read the table periodically. Failures are logged, never fatal."""
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await load_saved(db)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # table missing before the first migration, database restarting...
            logger.warning("settings refresh failed: %s", e)
        await asyncio.sleep(REFRESH_SECONDS)


def validate_changes(changes: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce every value; raise SettingValidationError listing all problems at once."""
    clean, problems = {}, []
    for key, raw in changes.items():
        defn = registry.BY_KEY.get(key)
        if defn is None:
            problems.append(f"Unknown setting '{key}'")
            continue
        try:
            value = registry.coerce(defn, raw)
        except registry.SettingValidationError as e:
            problems.append(str(e))
            continue
        if defn.type == "secret" and not value:
            continue          # a blank key field means "keep the saved key"; use reset to remove it
        clean[key] = value
    if problems:
        raise registry.SettingValidationError("; ".join(problems))
    return clean


async def save(db: AsyncSession, changes: Dict[str, Any], user_id: Optional[int]) -> None:
    """Persist values; a value equal to the default removes its row so defaults stay upgradable."""
    for key, value in changes.items():
        defn = registry.BY_KEY[key]
        existing = await db.get(AppSetting, key)
        if defn.type == "secret":
            value = secret_store.encrypt(value)        # API keys are never stored in clear text
        if value == defn.default:
            if existing is not None:
                await db.delete(existing)
        elif existing is None:
            db.add(AppSetting(key=key, value=value, updated_by=user_id))
        else:
            existing.value, existing.updated_by = value, user_id
    await db.commit()
    await load_saved(db)


async def reset(db: AsyncSession, keys: Optional[Iterable[str]] = None) -> None:
    stmt = delete(AppSetting)
    if keys is not None:
        stmt = stmt.where(AppSetting.key.in_(list(keys)))
    await db.execute(stmt)
    await db.commit()
    await load_saved(db)


def describe(only_public: bool = False) -> List[Dict[str, Any]]:
    """Registry plus current values, shaped for the Settings page."""
    saved = set(settings.saved_keys())
    out = []
    for d in registry.REGISTRY:
        if only_public and not d.public:
            continue
        item = {
            "key": d.key, "group": d.group, "type": d.type, "label": d.label, "help": d.help,
            "value": getattr(settings, d.attr), "default": d.default, "saved": d.key in saved,
            "min": d.min, "max": d.max, "choices": list(d.choices), "advanced": d.advanced,
        }
        if d.type == "secret":      # the key itself never leaves the server, only whether one is saved
            item["configured"] = bool(item["value"])
            item["value"] = ""
        out.append(item)
    return out
