"""Post a tender's analysis result to Microsoft Teams (a Teams Workflows webhook from Settings > Tender Analysis).

The message is sent as {"html": "..."}, the same shape the n8n Tender Tiger summary uses with the same webhook.
"""
import asyncio
import html
import logging
from datetime import date
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.services.tender_tiger.doc_picker import where

logger = logging.getLogger(__name__)

_ICON = {"ELIGIBLE": "✅", "PARTIAL": "⚠️", "PENDING": "⚠️", "NOT_ELIGIBLE": "❌"}
_LABEL = {"ELIGIBLE": "ELIGIBLE", "PARTIAL": "PARTIALLY ELIGIBLE", "PENDING": "CANNOT CONFIRM YET", "NOT_ELIGIBLE": "NOT ELIGIBLE"}
_MAX_ITEMS = 5


def _e(v: Any) -> str:
    return html.escape(str(v if v is not None else ""))


def _due(d: Optional[date]) -> str:
    if not d:
        return "Due date not given"
    left = (d - date.today()).days
    tail = "closed" if left < 0 else "today" if left == 0 else f"{left} day{'s' if left != 1 else ''} left"
    return f"Due {d.strftime('%d %b %Y')} ({tail})"


def _names(items: List[Dict[str, Any]]) -> str:
    return ", ".join(_e(i["name"]) for i in items) or "none"


def _list(rows: List[Dict[str, Any]], page_map: List[Dict[str, Any]], what: str) -> str:
    out = []
    for r in rows[:_MAX_ITEMS]:
        place = where(r.get("page_no"), page_map)
        asks, has = r.get("tender_value") or r.get("required"), r.get("company_value")
        name = r.get("criterion") or r.get("field")
        line = f"<b>{_e(name)}</b>"
        if asks and str(name or "").rstrip("….").strip().lower() not in str(asks).lower():
            line += f": tender asks {_e(asks)}"
        if has and what == "fail":
            line += f" (we have {_e(has)})"
        if place:
            line += f" <i>[{_e(place)}]</i>"
        out.append(f"<li>{line}</li>")
    more = len(rows) - _MAX_ITEMS
    if more > 0:
        out.append(f"<li>+{more} more in the report</li>")
    return "<ul>" + "".join(out) + "</ul>"


def card(tender: Dict[str, Any], job: Dict[str, Any], report: Optional[Dict[str, Any]], minutes: Optional[float]) -> str:
    """The HTML message for one tender. `job` is the queue row, `report` the eligibility report (None when it did not finish)."""
    title = (tender.get("tender_title") or "Untitled tender")[:160]
    head = f"{_e(title)}, {_e(tender.get('organization') or 'organisation not listed')} (TID {_e(job['tid'])})"
    docs = job.get("documents") or {}
    analysed, skipped = docs.get("analyse", []), docs.get("skipped", [])
    base = (settings.ZYNEX_PUBLIC_URL or "").rstrip("/")
    lines = [f"<p>🐯 <b>Tender analysed — {head}</b></p>" if job["status"] == "done" else
             f"<p>🛑 <b>Tender analysis {'stopped' if job['status'] == 'stopped' else 'not done'} — {head}</b></p>",
             f"<p>📅 {_e(_due(tender.get('due_date')))}"]
    if analysed:
        unsure = [a for a in analysed if a.get("role") == "unsure"]
        lines.append(f"<br>📄 <b>Documents checked:</b> {_names(analysed)}"
                     + (f" (unsure: {_names(unsure)})" if unsure else "")
                     + (" — main document guessed" if docs.get("guessed") else ""))
    if skipped:
        lines.append(f"<br>⏭️ <b>Skipped:</b> {_names(skipped[:8])}{f' +{len(skipped) - 8} more' if len(skipped) > 8 else ''}")
    lines.append("</p>")

    if job["status"] == "done" and report:
        counts = (report.get("compliance_matrix") or {}).get("counts") or {}
        status = report.get("status") or "PENDING"
        must = counts.get("mandatory") or counts.get("total") or 0
        if status == "PARTIAL" and not counts.get("pass"):
            status = "PENDING"          # as on the ZYNEX screens: nothing confirmed yet is "cannot confirm", not "partial"
        lines.append(f"<p>{_ICON.get(status, '⚠️')} <b>Result: {_LABEL.get(status, status)}</b> — "
                     f"{counts.get('pass', 0)} of {must} must-haves met"
                     + (f" · {minutes:.0f} min" if minutes else "") + "</p>")
        rows = ((report.get("criteria") or {}).get("criteria")) or []
        page_map = docs.get("page_map") or []
        fail = [r for r in rows if r.get("status") == "FAIL"]
        missing = [r for r in rows if r.get("status") == "MISSING"]
        if fail:
            lines.append("<p>❌ <b>Not met</b></p>" + _list(fail, page_map, "fail"))
        review = [r for r in rows if r.get("status") == "NEEDS_REVIEW"]
        if missing:
            lines.append("<p>❓ <b>Needs data</b></p>" + _list(missing, page_map, "missing"))
        if review:
            lines.append("<p>🔎 <b>Check by hand</b></p>" + _list(review, page_map, "review"))
    else:
        lines.append(f"<p>⚠️ <b>Reason:</b> {_e(job.get('reason') or 'unknown')}"
                     + (f" (stopped at step {_e(job['stage'])})" if job.get("stage") else "") + "</p>")
        lines.append(f"<p>🔁 To analyse it again: open ZYNEX → Tender Analysis → Tender Tiger → \"Automatic analysis\" → "
                     f"TID {_e(job['tid'])} → \"Analyse again\" (runs without the time limit).</p>")
    if base:
        link = f"{base}/tender/report/{job['report_id']}" if job.get("report_id") and job["status"] == "done" \
            else f"{base}/tender/tiger/{job['tid']}"
        lines.append(f'<p><a href="{_e(link)}">Open in ZYNEX</a></p>')
    return "".join(lines)


async def send(message_html: str) -> Optional[str]:
    """Post to the Teams webhook. Returns None when sent, else the error (also when no webhook is set)."""
    url = (settings.TEAMS_WEBHOOK_URL or "").strip()
    if not url:
        return "No Teams webhook is set (Settings > Tender Analysis)."
    error = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(url, json={"html": message_html})
            if r.status_code < 300:
                return None
            error = f"Teams answered HTTP {r.status_code}: {r.text[:200]}"
        except httpx.HTTPError as e:
            error = f"Could not reach Teams: {type(e).__name__}"
        await asyncio.sleep(5 * (attempt + 1))
    logger.warning("Teams card not sent: %s", error)
    return error
