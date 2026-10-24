"""S8 - align every requirement with what the company knowledge base can actually answer.

For each criterion this records (a) which knowledge-base entity answers it and whether that entity holds any data,
(b) the requirement in a canonical form (rupees, years, a financial-year window, certificate names, technology names),
(c) for experience requirements, the domains the tender asks for and the company projects that match them, and
(d) for certificates, the recorded certificates that satisfy each name. The rule engine (S9) uses this instead of
re-deriving it, and the stage artifact shows an auditor exactly how each requirement was read.
"""
from typing import Any, Dict, List, Tuple

from app.schemas.eligibility import CriterionSchema
from app.services.eligibility import rule_engine as re_
from app.services.eligibility.company_facts import CompanyFacts
from app.services.eligibility.domain_vocab import canonical_tech, domains_in, text_has_domain
from app.services.eligibility.normalizer import Normalizer

_PROJECT_FIELDS = {"project_value", "similar_work_value", "contract_count", "govt_psu_experience"}
_ENTITY_OF = {
    "annual_turnover": "financial_records", "net_worth": "financial_records", "working_capital": "financial_records",
    "profit_after_tax": "financial_records", "team_role_count": "employees",
    "security_controls": "technologies", "os_db_requirement": "technologies",
}


def _entity(c: CriterionSchema, handler_kind: str) -> str:
    if c.field in _ENTITY_OF:
        return _ENTITY_OF[c.field]
    if c.field in _PROJECT_FIELDS:
        return "projects"
    if c.field in re_._CERT_FIELDS:
        return "certifications"
    return {"document": "none (document to submit)", "informational": "none (procedural term)"}.get(handler_kind, "company_profile")


def _has_data(entity: str, facts: CompanyFacts) -> bool:
    return {
        "financial_records": bool(facts.turnover_by_fy), "employees": bool(facts.employee_count),
        "projects": bool(facts.projects), "certifications": bool(facts.certifications),
        "technologies": bool(facts.technologies),
    }.get(entity, False)               # company_profile (incorporation, offices, blacklisting...) is not recorded yet


class CompanyAligner:
    @classmethod
    def align(cls, criteria: List[CriterionSchema], facts: CompanyFacts) -> Tuple[List[CriterionSchema], Dict[str, Any]]:
        summary: List[Dict[str, Any]] = []
        for c in criteria:
            try:
                info = cls._align_one(c, facts)
            except Exception as e:                       # alignment is an aid: it must never stop the evaluation
                info = {"entity": "unknown", "has_data": False, "notes": [f"alignment error: {type(e).__name__}"]}
            c.alignment = info
            summary.append({"id": c.criterion_id, "field": c.field, **{k: v for k, v in info.items() if k != "records"}})
        by_entity: Dict[str, int] = {}
        for item in summary:
            by_entity[item["entity"]] = by_entity.get(item["entity"], 0) + 1
        return criteria, {"by_entity": by_entity,
                          "answerable": sum(1 for s in summary if s.get("has_data")),
                          "no_company_data": [s["id"] for s in summary
                                              if s["entity"] not in ("none (document to submit)", "none (procedural term)")
                                              and not s.get("has_data")],
                          "criteria": summary}

    @classmethod
    def _align_one(cls, c: CriterionSchema, facts: CompanyFacts) -> Dict[str, Any]:
        handler = re_.RuleEngine._handler(c)
        kind = ("document" if handler is re_._document else "informational" if handler is re_._informational else "fact")
        entity = _entity(c, kind)
        info: Dict[str, Any] = {"entity": entity, "has_data": _has_data(entity, facts), "notes": []}
        src = c.source_text or ""

        if entity == "financial_records":
            required, op, problem = re_._threshold(c)
            info["normalized"] = ({"kind": "amount_inr", "op": op, "value": required, "display": re_._fmt_money(required)}
                                  if required is not None else {"kind": "amount_inr", "problem": problem})
            window = re_._years_window(src)
            pair = re_._any_n_of_m(src)
            mode = ("any_n_of_m" if pair else "cumulative" if window and "cumulative" in src.lower()
                    or window and "aggregate" in src.lower() else "average" if "average" in src.lower()
                    else "each_year" if window and window > 1 and any(w in src.lower() for w in ("each", "every")) else "latest")
            info["window"] = {"mode": mode, "years": window, "any_n_of_m": list(pair) if pair else None,
                              "named_fy": [f"FY{y - 1}-{str(y)[2:]}" for y in re_._tender_fy_years(src)]}
            info["records"] = len(facts.turnover_by_fy)
        elif entity == "projects":
            required, op, problem = re_._threshold(c)
            if required is not None:
                info["normalized"] = {"kind": "amount_inr" if "value" in c.field else "count", "op": op,
                                      "value": required, "display": re_._fmt_money(required)}
            domains = domains_in(src + " " + (" ".join(map(str, c.value)) if isinstance(c.value, (list, tuple)) else str(c.value)))
            info["domains"] = domains
            if domains:
                matched = [p for p in facts.completed_projects if text_has_domain(p.searchable_text, domains)]
                info["matched_records"] = [{"name": p.name, "value": p.value} for p in matched]
                if not matched:
                    info["notes"].append("no recorded completed project is described as " + " / ".join(domains))
            info["records"] = len(facts.completed_projects)
        elif entity == "certifications":
            names = re_._cert_names(c)
            resolved = []
            for n in names:
                level = re_._cmmi_level(n)
                if level is not None:
                    hits = [cf.name for cf in facts.certifications if "cmmi" in cf.name.lower() and (re_._cmmi_level(cf.name) or 0) >= level]
                else:
                    key = re_._cert_key(n)
                    hits = [cf.name for cf in facts.certifications if key and re_._cert_matches(key, cf.name)]
                resolved.append({"required": n, "recorded_as": hits})
            info["normalized"] = {"kind": "certificates", "items": resolved}
            info["records"] = len(facts.certifications)
        elif entity == "technologies":
            items = [str(x) for x in (c.value if isinstance(c.value, (list, tuple)) else [c.value]) if str(x).strip()]
            info["normalized"] = {"kind": "technologies", "items": [{"required": i, "canonical": canonical_tech(i)} for i in items]}
            info["records"] = len(facts.technologies)
        elif entity == "employees":
            info["normalized"] = {"kind": "headcount", "value": Normalizer.parse_numeric(c.value)}
            info["records"] = facts.employee_count or 0
        elif c.field == "experience_years":
            info["normalized"] = {"kind": "years", "value": Normalizer.parse_numeric(c.value)}
            info["domains"] = domains_in(src)
            info["notes"].append("years in business are not recorded in the knowledge base")
        return info
