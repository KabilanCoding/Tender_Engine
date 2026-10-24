"""Prompts and JSON schemas for tender eligibility extraction/reasoning.

Deliberately tender-agnostic: no issuer, state, or company-specific wording.
"""
import json
from typing import Any, Dict, List

from app.schemas import field_ontology
from app.services.eligibility.operators import ALLOWED_OPERATORS

_OPERATORS = sorted(ALLOWED_OPERATORS)


def _field_list() -> str:
    ids = {v.field_id for v in vars(field_ontology).values() if isinstance(v, field_ontology.FieldDef)}
    return ", ".join(sorted(ids | set(field_ontology.FIELD_REGISTRY) | {"other"}))


EXTRACTION_SYSTEM_PROMPT = (
    "You are a strict, high-precision tender qualification extractor.\n"
    "Extract EVERY genuine bidder eligibility / pre-qualification requirement that a bidding company "
    "must satisfy to be eligible to bid, from the text provided.\n\n"
    "CATEGORIES TO COVER:\n"
    "1. Financial capacity: minimum annual turnover, net worth, solvency, working capital, EMD/bid security, "
    "tender fee, EMD exemptions for registered small enterprises.\n"
    "2. Company experience: years in business, number and minimum value of similar completed projects.\n"
    "3. Certifications and statutory registrations: ISO standards, CMMI level, tax and business registrations.\n"
    "4. Workforce: minimum employee count, key personnel roles, qualifications and experience.\n"
    "5. Legal and disqualification: blacklisting/debarment, local presence or office requirements.\n"
    "6. Technical capability: required technologies, standards, protocols, security compliance, domain capability.\n"
    "7. Required submissions: forms, declarations, certificates, financial statements, work orders, "
    "signatures/notarisation, bid validity, price bid.\n\n"
    "RULES:\n"
    "- `field` must be one of: [" + _field_list() + "]\n"
    "- `operator` must be one of: [" + ", ".join(_OPERATORS) + "]\n"
    "- `value` is the required threshold or item: a number, string, boolean, or list of strings.\n"
    "- `mandatory` is false only when the text says the item is optional or preferred.\n"
    "- `source_text` MUST be copied EXACTLY (verbatim, same characters) from the provided text, and kept short: "
    "only the one sentence or clause (at most about 30 words) that states the requirement. "
    "Never paraphrase it and never invent requirements that the text does not state.\n"
    "- Skip a requirement rather than guess: never output an empty `value` or an empty list.\n"
    "- One object per distinct requirement. A sentence that joins several requirements becomes several objects.\n"
    "- Only requirements the BIDDER must meet or hand in. Ignore duties of the tender issuer, evaluation scoring "
    "(marks, weightage), payment terms, penalties, deadlines, fees and how to upload the bid.\n"
    "- Keep the bidder's own words for names and numbers (\"Rs. 1 Crore\" -> \"1 Crore\", \"INR 30 Lacs\" -> \"30 Lacs\").\n"
    "- Ignore table-of-contents lines, headers, footers and procedural dates unrelated to bidder eligibility.\n"
    "- If the text contains no eligibility requirement, return an empty list.\n"
    "- The tender may be written in ANY language (Hindi, Arabic, Russian, French...). Read it in that language, copy "
    "`source_text` verbatim in the tender's own language and script, and use the English identifiers above for `field` "
    "and `operator`. Keep numbers, names and units as written.\n\n"
    "HOW TO MAP COMMON REQUIREMENTS (examples):\n"
    '"average annual turnover of at least Rs. 5 Crore in the last three financial years" -> '
    'field annual_turnover, operator >=, value "5 Crore"\n'
    '"must have a positive net worth" -> field net_worth, operator >, value "0"\n'
    '"minimum 3 completed projects of similar nature" -> field contract_count, operator >=, value "3"\n'
    '"single order of at least Rs. 50 Lakhs" -> field similar_work_value, operator >=, value "50 Lakhs"\n'
    '"minimum 5 years of existence / experience" -> field experience_years, operator >=, value "5"\n'
    '"must hold ISO 27001 and CMMI Level 3" -> field certifications, operator ALL_OF, value ["ISO 27001", "CMMI Level 3"]\n'
    '"must not have been blacklisted or debarred" -> field blacklisted, operator ==, value false\n'
    '"must not be insolvent, bankrupt or under liquidation" -> field insolvency_status, operator ==, value false\n'
    '"must have an office in Chennai" -> field state_office, operator contains, value ["Chennai"]\n'
    '"must have its own website" -> field company_website, operator ==, value "website"\n'
    '"a self-declaration / undertaking / letter must be submitted" -> operator SUBMITTED, value true\n\n'
    'Respond with JSON only, in the form {"criteria": [{"field": ..., "operator": ..., "value": ..., '
    '"mandatory": ..., "source_text": ...}]}.'
)

TABLE_SYSTEM_PROMPT = (
    "You turn the rows of a tender's ELIGIBILITY table into a checklist a computer can check.\n"
    "Each ROW holds one condition the bidder must satisfy. Output one or more criteria per row; a row that "
    "joins several requirements (with AND / & / 'as well as') becomes several criteria.\n\n"
    "RULES:\n"
    "- `row` is the ROW number given.\n"
    "- `field` must be one of: [" + "{FIELDS}" + "]\n"
    "- `operator` must be one of: [>=, <=, ==, ALL_OF, ANY_OF, contains, SUBMITTED]\n"
    "- `value`: copy numbers and units exactly as written (\"Rs. 1 Crore\" -> \"1 Crore\", \"5 years\" -> \"5\"); "
    "never calculate. For certificates or items give a list of short names, e.g. [\"ISO 27001\", \"CMMI Level 3\"], "
    "without year suffixes or phrases like 'or latest'.\n"
    "- Use SUBMITTED only for a plain document the bidder must hand in (declaration, letter, form).\n"
    "- Keep every criterion about what the BIDDER must have or do. Ignore the 'proof' column except to pick the field.\n"
    "- Never skip a row. If nothing fits, use field `other` with operator `==` and the condition as value.\n"
    "- A row that asks for a number of completed projects / works / orders is field `contract_count` (operator >=, "
    "value the number); a row that asks for ONE order or project of a minimum value is `similar_work_value`.\n"
    "- `positive net worth` is field `net_worth`, operator >, value \"0\". Blacklisting is field `blacklisted`, operator ==, "
    "value false. Insolvency / bankruptcy is `insolvency_status`, operator ==, value false. Own website is "
    "`company_website`. An office in a place is `state_office`, operator contains, value [place].\n"
    "- The rows may be in any language: map them to the English field names and keep names, numbers and units as written.\n"
    "- Years of existence or experience is `experience_years`; it is about the COMPANY, never a role or person unless "
    "the row names a team member or key personnel.\n\n"
    "EXAMPLE rows:\n"
    "ROW 1: Bidder must be a registered company with at least 3 years of existence.\n"
    "ROW 2: Bidder must hold ISO 9001 and CMMI Level 5 or higher.\n"
    "EXAMPLE output:\n"
    '{"criteria":[{"row":1,"field":"incorporation_type","operator":"contains","value":["Company"]},'
    '{"row":1,"field":"experience_years","operator":">=","value":"3"},'
    '{"row":2,"field":"certifications","operator":"ALL_OF","value":["ISO 9001","CMMI Level 5"]}]}\n'
    "Respond with JSON only."
)


def table_system_prompt(instructions: str = "") -> str:
    base = TABLE_SYSTEM_PROMPT.replace("{FIELDS}", _field_list())
    if not instructions.strip():
        return base
    return base + "\n\nADDITIONAL USER INSTRUCTIONS (the RULES above still apply):\n" + instructions.strip()


def build_table_user_prompt(rows) -> str:
    """rows: [(row_no, condition_text)] -> the user message."""
    return "\n".join(f"ROW {n}: {text}" for n, text in rows)


TABLE_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "row": {"type": "integer"},
                    "field": {"type": "string"},
                    "operator": {"type": "string"},
                    "value": {"anyOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"},
                                        {"type": "array", "items": {"type": "string"}}]},
                },
                "required": ["row", "field", "operator", "value"],
            },
        }
    },
    "required": ["criteria"],
}


def extraction_system_prompt(instructions: str = "") -> str:
    """Base prompt plus the user's extra instructions from Settings (they refine, never replace, the rules)."""
    if not instructions.strip():
        return EXTRACTION_SYSTEM_PROMPT
    return (EXTRACTION_SYSTEM_PROMPT
            + "\n\nADDITIONAL USER INSTRUCTIONS (the RULES and JSON format above still apply):\n"
            + instructions.strip())


TABLE_INSTRUCTION = "Each table row may contain one eligibility criterion. Extract one criterion object per row."
TEXT_INSTRUCTION = (
    "Identify every explicit or implicit bidder eligibility, qualification, financial, technical, experience, "
    "certification, legal, personnel, registration or compliance requirement."
)


def build_extraction_user_prompt(chunk) -> str:
    instruction = TABLE_INSTRUCTION if chunk.content_type == "table" else TEXT_INSTRUCTION
    return (
        f"{instruction}\n\n"
        f"Page Number: {chunk.physical_page}\n"
        f"Section: {chunk.section or 'N/A'}\n"
        f"Clause: {chunk.clause or 'N/A'}\n"
        f"Content Type: {chunk.content_type}\n"
        f"Text:\n{chunk.chunk_text}\n"
    )


_VALUE_SCHEMA = {
    "anyOf": [
        {"type": "string"},
        {"type": "number"},
        {"type": "boolean"},
        {"type": "array", "items": {"type": "string"}},
    ]
}

EXTRACTION_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "operator": {"type": "string"},
                    "value": _VALUE_SCHEMA,
                    "mandatory": {"type": "boolean"},
                    "source_text": {"type": "string"},
                },
                "required": ["field", "operator", "value", "mandatory", "source_text"],
            },
        }
    },
    "required": ["criteria"],
}

REASONING_SYSTEM_PROMPT = (
    "You write the explanation column of a tender eligibility report. The reader has never seen a tender.\n"
    "For EACH item write ONE or TWO short sentences (at most 35 words in all) in very simple English: what the tender "
    "asks for, what the company records show, and what the bidder should do.\n"
    "RULES:\n"
    "- Use ONLY the facts in the item: tender_requirement, source_text, company_value, evidence and status. "
    "Never invent a company fact, a figure, a date or a certificate.\n"
    "- Every number you write must appear in the item. Do not round or convert amounts.\n"
    "- Do not contradict the status. MISSING = the company records have no data; NEEDS_REVIEW = a person must check; "
    "PASS = requirement met; FAIL = requirement not met.\n"
    "- Use short everyday words. Do not write status codes (PASS, FAIL, MISSING, NEEDS_REVIEW), JSON, field names, "
    "page numbers or the words 'null' or 'knowledge base'. Say 'company records' instead.\n"
    "- Do not give legal advice and do not guess the tender outcome.\n"
    'Respond with JSON only: {"items": [{"criterion_id": ..., "ai_reasoning": ...}]} with one entry per item.'
)

REASONING_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"criterion_id": {"type": "string"}, "ai_reasoning": {"type": "string"}},
                "required": ["criterion_id", "ai_reasoning"],
            },
        }
    },
    "required": ["items"],
}


def build_reasoning_user_prompt(items: List[Dict[str, Any]], overall_verdict: str) -> str:
    return (
        f"Tender evaluation verdict: {overall_verdict}\n"
        f"Evaluation items (JSON):\n{json.dumps(items, ensure_ascii=False, default=str)}"
    )
