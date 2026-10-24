"""TEMPORARY step-by-step trace of a tender analysis, for checking each step by hand.

Switched on by Settings > System > "Save a trace of every analysis" (off by default). When on, every run writes plain-text files to
<uploads>/trace/run_<id>_<file>/ : the text read from each page, OCR, structure, chunks, what was read or skipped, every question sent
to the AI and its raw answer, the requirements and checklist items kept and dropped, and one .docx with everything.
Remove this module and its few call sites when the check is finished. It never changes a result and never raises.
"""
import contextvars
import json
import os
import re
from typing import Any, Dict, List, Optional

from app.core.config import settings

_current: "contextvars.ContextVar[Optional[Trace]]" = contextvars.ContextVar("zynex_trace", default=None)


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text or "file")[:60]


class Trace:
    def __init__(self, path: str):
        self.path = path
        self.calls = 0
        self.page_chars: Dict[int, int] = {}
        self.read_pages: Dict[int, str] = {}
        self.criteria_pages: Dict[int, int] = {}
        self.checklist_pages: Dict[int, int] = {}
        os.makedirs(path, exist_ok=True)

    def write(self, rel: str, text: str) -> None:
        try:
            full = os.path.join(self.path, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass


def start(run_key: Any, filename: str) -> Optional[Trace]:
    """Begin a trace for this run (call inside the task that runs the analysis). Returns None when tracing is off."""
    try:
        if not getattr(settings, "TRACE_RUNS", False):
            _current.set(None)
            return None
        t = Trace(os.path.join(settings.UPLOAD_DIR, "trace", f"run_{run_key}_{_slug(filename)}"))
        _current.set(t)
        return t
    except Exception:
        _current.set(None)
        return None


def get() -> Optional[Trace]:
    return _current.get()


def write(rel: str, text: str) -> None:
    t = _current.get()
    if t:
        t.write(rel, text)


def ai_call(label: str, system: str, user: str, response: str, error: str = "") -> None:
    t = _current.get()
    if not t:
        return
    t.calls += 1
    t.write(f"10_ai_calls/call_{t.calls:03d}_{label}.txt",
            f"=== SYSTEM PROMPT (instructions given to the AI) ===\n{system}\n\n=== TEXT SENT (the document part the AI read) ===\n{user}\n\n"
            f"=== AI ANSWER (raw) ===\n{response if not error else 'FAILED: ' + error}\n")


# ── writers for each step ───────────────────────────────────────────────────────────────────────

def file_check(info: Dict[str, Any]) -> None:
    write("01_file_check.txt", "S1 FILE CHECK\n\n" + json.dumps(info, indent=2, ensure_ascii=False, default=str))


def pages_text(pages: List[Dict[str, Any]], folder: str, title: str, only_ocr: bool = False) -> None:
    t = _current.get()
    if not t:
        return
    for p in pages:
        no = p.get("page_no")
        if only_ocr and not p.get("ocr_used"):
            continue
        lines = [f"{title}: PAGE {no}  |  characters: {p.get('char_count')}  |  scanned: {p.get('is_scanned')}  |  OCR used: {p.get('ocr_used', False)}", "-" * 70]
        for b in p.get("blocks", []):
            tag = "[table] " if b.get("type") == "table" else "[heading] " if b.get("is_heading") else ""
            lines.append(tag + str(b.get("text", "")))
        t.write(f"{folder}/page_{int(no):03d}.txt", "\n".join(lines) + "\n")
        if folder.startswith("02"):
            t.page_chars[int(no)] = int(p.get("char_count") or 0)


def structure(nodes: List[Dict[str, Any]]) -> None:
    out = [f"S3 STRUCTURE: {len(nodes)} parts found (type, page, text)\n"]
    for n in nodes:
        out.append(f"[{n.get('type')}] page {n.get('page_no')}: {str(n.get('text', ''))[:400]}")
    write("04_structure.txt", "\n".join(out) + "\n")


def chunks(chunks_: List[Any]) -> None:
    t = _current.get()
    if not t:
        return
    idx = ["S4 CHUNKS: the pieces the document is cut into (each is sent to the next steps as one unit)\n"]
    for i, c in enumerate(chunks_, start=1):
        head = (f"CHUNK {i}  id={c.chunk_id}  page={c.physical_page}  type={c.content_type}  chars={c.char_count}"
                f"  chapter={c.chapter}  section={c.section}  clause={c.clause}")
        t.write(f"05_chunks/chunk_{i:03d}_p{c.physical_page:03d}.txt", head + "\n" + "-" * 70 + "\n" + c.chunk_text + "\n")
        idx.append(head)
    t.write("05_chunks_index.txt", "\n".join(idx) + "\n")


def read_or_skipped(rows: List[str], plan: Dict[str, Any], page_decision: Dict[int, str]) -> None:
    t = _current.get()
    if t:
        t.read_pages.update(page_decision)
    write("06_what_was_read_or_skipped.txt",
          "S5/S6 WHAT THE AI READ FOR ELIGIBILITY, AND WHAT WAS SKIPPED (with the reason)\n\nPLAN: "
          + json.dumps(plan, indent=2, ensure_ascii=False, default=str) + "\n\nPER CHUNK\n" + "\n".join(rows) + "\n")


def raw_criteria(raw: List[Any]) -> None:
    t = _current.get()
    out = [f"S6 RAW REQUIREMENTS the AI listed: {len(raw)}\n"]
    for c in raw:
        out.append(f"{c.criterion_id} | page {c.page_no} | field={c.field} | operator={c.operator} | value={c.value}\n    quote: {c.source_text}")
        if t:
            t.criteria_pages[c.page_no] = t.criteria_pages.get(c.page_no, 0) + 1
    write("07a_raw_requirements.txt", "\n".join(out) + "\n")


def validated(raw: List[Any], kept: List[Any], metrics: Dict[str, Any]) -> None:
    keep_quotes = {(c.page_no, c.source_text) for c in kept}
    out = ["S7 QUOTE CHECK: each requirement's quote must be found word for word on its page\n", "METRICS: " + json.dumps(metrics, ensure_ascii=False, default=str), "\nKEPT"]
    for c in kept:
        out.append(f"{c.criterion_id} | page {c.page_no} | quote found word for word: {c.exact_match} | field={c.field} | value={c.value}\n    quote: {c.source_text}")
    out.append("\nNOT KEPT (rejected as duplicate, noise, or quote not found)")
    for c in raw:
        if (c.page_no, c.source_text) not in keep_quotes:
            out.append(f"{c.criterion_id} | page {c.page_no} | field={c.field} | value={c.value}\n    quote: {c.source_text}")
    write("07b_checked_requirements.txt", "\n".join(out) + "\n")


def comparison(results: List[Any]) -> None:
    out = ["S8/S9 EACH REQUIREMENT COMPARED WITH THE COMPANY RECORDS\n"]
    for r in results:
        out.append(f"{r.criterion_id} | page {r.page_no} | {r.status} | field={r.field}\n    tender asks: {r.tender_value}\n    company has: {r.company_value}\n    evidence: {r.evidence}\n    quote: {r.source_text}")
    write("08_company_comparison.txt", "\n".join(out) + "\n")


def checklist(out: Dict[str, Any], dropped: List[Dict[str, Any]]) -> None:
    t = _current.get()
    labels = out.get("labels", {})
    lines = [f"S11 FULL CHECKLIST: {len(out['items'])} items\nMETRICS: {json.dumps(out.get('metrics', {}))}\n"]
    for cat in labels:
        its = [i for i in out["items"] if i["category"] == cat]
        if its:
            lines.append(f"\n== {labels[cat]} ({len(its)}) ==")
            lines += [f"{i['id']} | page {i['page']} | {'compared with company records' if i.get('compared') else ''}\n    {i['text']}" for i in its]
    lines.append("\n\n== DROPPED (the AI listed them but they could not be matched word for word to the tender, or were duplicates/too short) ==")
    lines += [f"[{d['reason']}] ({d['category']}) {d['text']}" for d in dropped]
    write("09_full_checklist.txt", "\n".join(lines) + "\n")
    if t:
        for i in out["items"]:
            t.checklist_pages[i["page"]] = t.checklist_pages.get(i["page"], 0) + 1


def finish(filename: str) -> Optional[str]:
    """Summary table and one combined .docx. Returns the folder."""
    t = _current.get()
    if not t:
        return None
    pages = sorted(set(t.page_chars) | set(t.read_pages) | set(t.checklist_pages) | set(t.criteria_pages))
    rows = ["PAGE | CHARACTERS READ | ELIGIBILITY STEP | REQUIREMENTS FROM PAGE | CHECKLIST ITEMS FROM PAGE", "-" * 100]
    for p in pages:
        flag = "   <-- no checklist items: check this page yourself" if not t.checklist_pages.get(p) else ""
        rows.append(f"{p:>4} | {t.page_chars.get(p, 0):>8} | {t.read_pages.get(p, '-'):<42} | {t.criteria_pages.get(p, 0):>3} | {t.checklist_pages.get(p, 0):>3}{flag}")
    t.write("00_SUMMARY.txt", f"TRACE of {filename}\nOpen page N of the PDF beside 02_text_per_page/page_NNN.txt, then the chunk and checklist files.\n\n" + "\n".join(rows) + "\n")
    try:
        from docx import Document
        doc = Document()
        doc.add_heading(f"Trace: {filename}", 0)
        for root, _dirs, files in sorted(os.walk(t.path)):
            for fn in sorted(files):
                if fn.endswith(".txt"):
                    rel = os.path.relpath(os.path.join(root, fn), t.path)
                    doc.add_heading(rel, 2)
                    with open(os.path.join(root, fn), encoding="utf-8") as f:
                        for line in f.read().split("\n"):
                            doc.add_paragraph(line)
        doc.save(os.path.join(t.path, "ALL_STEPS.docx"))
    except Exception:
        pass
    return t.path
