"""Key dates of a tender and whether they have passed, read by rule from the text (no AI).

A bid is wasted if the deadline has already gone by, so this is the first thing a person checks. The dates come from the tender's own
fact sheet / notice lines such as "Last date for submission of bids 28/09/2026 till 04:00 PM".
"""
import re
from datetime import date
from typing import Any, Dict, List, Optional

from app.schemas.eligibility import ChunkSchema

_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_DATE_NUM = re.compile(r"\b(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})\b")
_DATE_TXT = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b")
_TIME = re.compile(r"\b(\d{1,2}[:.]\d{2}\s*(?:[ap]\.?m\.?)?)", re.IGNORECASE)

# (kind, label pattern); the first kind that matches a line wins. 'deadline' is the one that decides whether a bid is still possible.
_KINDS = [
    ("pre-bid queries", re.compile(r"(?:last\s+date\s+(?:for|of)\s+)?(?:submission\s+of\s+)?pre-?bid\s+(?:queries|questions|clarifications?)", re.IGNORECASE)),
    ("deadline", re.compile(r"(?:last|final|closing)\s+(?:date|day)(?:\s+and\s+time)?\s*(?:for|of)\s+(?:the\s+)?(?:online\s+)?(?:submission|receipt|uploading)\s+(?:of\s+)?(?:e-?)?(?:bids?|tenders?|proposals?|eoi|expressions?)|"
                          r"bid\s+(?:submission|closing)\s+(?:date|deadline)|due\s+date\s+(?:for|of)\s+(?:bid|tender|proposal)|submission\s+deadline|"
                          r"last\s+date\s+(?:and\s+time\s+)?(?:for\s+)?(?:submission|receipt)|closing\s+date", re.IGNORECASE)),
    ("pre-bid meeting", re.compile(r"pre-?bid\s+(?:meeting|conference)", re.IGNORECASE)),
    ("technical bid opening", re.compile(r"opening\s+of\s+(?:the\s+)?(?:technical|pre-?qualification|eligibility)\s+(?:bids?|proposals?)|technical\s+bid\s+opening", re.IGNORECASE)),
    ("financial bid opening", re.compile(r"opening\s+of\s+(?:the\s+)?(?:financial|commercial|price)\s+(?:bids?|proposals?)", re.IGNORECASE)),
    ("publish date", re.compile(r"(?:tender|rfp|nit|bid)\s*(?:/\s*\w+\s*)?publi(?:sh|cation)\s+date|date\s+of\s+publication", re.IGNORECASE)),
]


def _parse_dates(text: str) -> List[date]:
    out: List[date] = []
    for d, m, y in _DATE_NUM.findall(text):
        try:
            out.append(date(int(y), int(m), int(d)))
        except ValueError:
            pass
    for d, mon, y in _DATE_TXT.findall(text):
        mm = _MONTHS.get(mon[:3].lower())
        if mm:
            try:
                out.append(date(int(y), mm, int(d)))
            except ValueError:
                pass
    return out


def find_key_dates(chunks: List[ChunkSchema], today: Optional[date] = None) -> List[Dict[str, Any]]:
    today = today or date.today()
    found: Dict[str, Dict[str, Any]] = {}
    for c in sorted(chunks, key=lambda c: (c.physical_page, c.chunk_id)):
        for raw in (c.chunk_text or "").split("\n"):
            line = re.sub(r"\s+", " ", raw).strip(" |")
            if not line or len(line) > 400:
                continue
            for kind, rx in _KINDS:
                if not rx.search(line):
                    continue
                dates = _parse_dates(line)
                if not dates:
                    break
                if kind in found and kind != "deadline":
                    break
                if kind == "deadline" and "deadline" in found and found["deadline"]["page"] != c.physical_page and found["deadline"]["date"] >= max(dates).isoformat():
                    break
                t = _TIME.search(line)
                d = max(dates) if kind == "deadline" else dates[0]
                days = (d - today).days
                found[kind] = {"kind": kind, "date": d.isoformat(), "time": t.group(1).strip() if t else None, "page": c.physical_page,
                               "quote": line[:300], "days_left": days,
                               "status": "passed" if days < 0 else "today" if days == 0 else "open"}
                break
    order = ["publish date", "pre-bid queries", "pre-bid meeting", "deadline", "technical bid opening", "financial bid opening"]
    return sorted(found.values(), key=lambda k: order.index(k["kind"]) if k["kind"] in order else 99)


def deadline_warning(key_dates: List[Dict[str, Any]]) -> Optional[str]:
    d = next((k for k in key_dates if k["kind"] == "deadline"), None)
    if not d:
        return None
    when = f"{d['date']}{' ' + d['time'] if d['time'] else ''}"
    if d["status"] == "passed":
        return (f"The last date to submit bids ({when}, page {d['page']}) passed {-d['days_left']} day(s) ago. Check the tender portal for an "
                "extension or corrigendum; otherwise this tender is closed and this analysis is for reference.")
    if d["status"] == "today":
        return f"The last date to submit bids is TODAY ({when})."
    if d["days_left"] <= 7:
        return f"Only {d['days_left']} day(s) left to submit bids (last date {when})."
    return None
