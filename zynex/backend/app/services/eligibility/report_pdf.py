"""Eligibility report as a PDF, rendered with PyMuPDF's Story (no WeasyPrint/GTK dependency)."""
import io
from html import escape
from typing import Any, Dict, List

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

_CSS = """
body { font-family: sans-serif; font-size: 9pt; color: #0f172a; }
h1 { font-size: 18pt; margin-bottom: 2pt; }
h2 { font-size: 12pt; margin-top: 14pt; margin-bottom: 4pt; color: #1e3a8a; }
p.meta { color: #475569; margin-top: 0; }
div.verdict { padding: 8pt; font-size: 13pt; font-weight: bold; margin: 8pt 0; }
table { width: 100%; border-collapse: collapse; }
th { background-color: #e2e8f0; text-align: left; padding: 3pt; font-size: 8pt; }
td { padding: 3pt; border-bottom: 0.5pt solid #cbd5e1; vertical-align: top; font-size: 8pt; }
.PASS { color: #047857; font-weight: bold; } .FAIL { color: #be123c; font-weight: bold; }
.MISSING { color: #b45309; font-weight: bold; } .NEEDS_REVIEW { color: #7c3aed; font-weight: bold; }
.INFORMATIONAL { color: #475569; }
li { margin-bottom: 2pt; }
"""

_VERDICT = {
    "PASS": ("ELIGIBLE", "#d1fae5"),
    "ELIGIBLE": ("ELIGIBLE", "#d1fae5"),
    "FAIL": ("NOT ELIGIBLE", "#ffe4e6"),
    "NOT_ELIGIBLE": ("NOT ELIGIBLE", "#ffe4e6"),
    "PARTIAL": ("CANNOT CONFIRM YET: some points need company data or a person to check", "#fef3c7"),
}


def _val(v: Any) -> str:
    if isinstance(v, (list, tuple)):
        return ", ".join(map(str, v))
    return "-" if v is None else str(v)


def _label(field) -> str:
    from app.services.eligibility.verdict import field_label
    return field_label(field)


def _required(r: Dict[str, Any]) -> str:
    from app.services.eligibility.verdict import requirement_text
    return requirement_text(r.get("operator"), r.get("tender_value"), r.get("source_text") or "")


def _title(r: Dict[str, Any]) -> str:
    from app.services.eligibility.verdict import plain_title
    return plain_title(r.get("field"), r.get("source_text") or "", r.get("tender_value"))


def build_report_pdf(report: Dict[str, Any]) -> bytes:
    """`report` is the dict served by GET /tender/{run}/report."""
    from app.services.eligibility.verdict import shorten, status_text
    label, colour = _VERDICT.get(report["verdict"], (report["verdict"], "#e2e8f0"))
    rows: List[str] = []
    info_rows: List[str] = []
    for r in report["results"]:
        (info_rows if r["status"] == "INFORMATIONAL" else rows).append(
            "<tr><td>{id}</td><td>{page}</td><td>{field}{opt}</td><td>{req}</td>"
            "<td class='{st}'>{stt}</td><td>{ev}</td></tr>".format(
                id=escape(str(r["criterion_id"])), page=r.get("page_no", ""),
                field=escape(_title(r)),
                opt="" if r.get("mandatory", True) else " <i>(not compulsory)</i>",
                req=escape(_required(r)),
                st=escape(r["status"]), stt=escape(status_text(r["status"])),
                ev=escape(shorten(r.get("reason") or r.get("evidence") or "", 400)),
            ))
    checklist = "".join(f"<li>{escape(item)}</li>" for item in report.get("action_checklist", []))
    m = report.get("metrics", {})
    full = report.get("full_checklist") or {}
    full_html = ""
    if full.get("items"):
        labels = full.get("labels", {})
        parts = []
        for cat in ("eligibility", "scope", "deliverables", "timeline", "commercial", "submission", "evaluation", "obligations"):
            its = [i for i in full["items"] if i["category"] == cat]
            if its:
                parts.append(f"<h3>{escape(labels.get(cat, cat))} ({len(its)})</h3><table><tr><th>ID</th><th>Pg</th><th>Word for word from the tender</th></tr>"
                             + "".join(f"<tr><td>{escape(i['id'])}</td><td>{i['page']}</td><td>{escape(i['text'])}</td></tr>" for i in its) + "</table>")
        note = " This list may be incomplete: part of the tender could not be read by the AI model." if full.get("incomplete") else ""
        full_html = ("<h2>Full tender checklist</h2><p class='meta'>Everything the tender asks for, read from the whole document, for you to compare "
                     "with your own records." + escape(note) + "</p>" + "".join(parts))
    html = f"""
    <h1>Tender Eligibility Report</h1>
    <p class='meta'>{escape(report['filename'])} &nbsp;|&nbsp; Run {escape(str(report['run_id']))}</p>
    <div class='verdict' style='background-color:{colour}'>{escape(label)}</div>
    <p>Must-have requirements: {report['mandatory_pass']} met, {report['mandatory_fail']} not met,
       {report['mandatory_missing']} with no company data, {report.get('mandatory_review_required', 0)} to check by hand;
       {report.get('documents_to_prepare', 0)} document(s) to prepare and attach.</p>
    <h2>Requirement by requirement</h2>
    <table><tr><th>ID</th><th>Pg</th><th>Requirement</th><th>What the tender asks</th><th>Result</th><th>Explanation</th></tr>
    {''.join(rows)}</table>
    {"<h2>What to do before bidding</h2><ol>" + checklist + "</ol>" if checklist else ""}
    {"<h2>Other terms in the tender (for information; the company does not have to prove these)</h2><table>" + "".join(info_rows) + "</table>" if info_rows else ""}
    {full_html}
    <p class='meta'>Made by ZYNEX. Pages read: {m.get('chunks_processed', '-')}.
       Results come from the company records. If something is not recorded, we say so and never guess.</p>
    """
    story = fitz.Story(html=html, user_css=_CSS)
    buf = io.BytesIO()
    writer = fitz.DocumentWriter(buf)
    mediabox = fitz.paper_rect("a4")
    where = mediabox + (36, 36, -36, -36)
    more = 1
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
    writer.close()
    return buf.getvalue()
