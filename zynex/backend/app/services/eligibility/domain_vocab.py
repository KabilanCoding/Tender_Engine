"""Tender-agnostic vocabulary used to line a tender requirement up with company records.

Domains: what kind of work a tender asks for experience in ("ERP / e-commerce solution"), matched against what the
knowledge base says each project was. Technology aliases: different spellings of the same technology.
"""
import re
from typing import Dict, Iterable, List

DOMAINS: Dict[str, List[str]] = {
    "ERP": ["erp", "enterprise resource planning", "enterprise management software"],
    "e-commerce": ["e-commerce", "ecommerce", "e commerce", "online marketplace", "online shopping", "e-procurement",
                   "eprocurement", "marketplace"],
    "web portal": ["web portal", "portal", "web application", "web-based application", "website"],
    "mobile application": ["mobile app", "mobile application", "android", "ios app", "flutter", "react native"],
    "GPS / vehicle tracking": ["gps", "vehicle tracking", "avls", "fleet tracking", "fleet management", "telematics", "gnss"],
    "IVRS": ["ivrs", "ivr", "interactive voice response"],
    "e-governance": ["e-governance", "egovernance", "e-gov", "citizen portal", "citizen services", "government portal"],
    "security audit": ["security audit", "cyber security", "cybersecurity", "information security audit", "vapt",
                       "penetration testing"],
    "cloud": ["cloud", "aws", "azure", "google cloud"],
    "payment / ticketing": ["payment gateway", "payments", "fare collection", "ticketing", "pos system", "point of sale"],
    "project management consultancy": ["project management consultancy", "pmc", "project management consultant"],
    "data centre / infrastructure": ["data centre", "data center", "network infrastructure", "server infrastructure"],
    "AI / analytics": ["artificial intelligence", "machine learning", "analytics", "business intelligence", "dashboard"],
    "railways / transit": ["railway", "railways", "rail", "train", "trains", "metro", "transit", "public transport", "passenger information",
                           "rolling stock", "cris", "icf", "coach tracking"],
    "smart city": ["smart city", "smart-city", "smart cities", "iccc", "command and control", "command & control", "urban local body", "intelligent traffic"],
    "healthcare": ["hospital", "hospitals", "healthcare", "health care", "hims", "medical", "patient", "telemedicine", "clinic"],
    "tax / revenue": ["tax e-filing", "e-filing", "property tax", "commercial tax", "revenue management", "e-ledger", "taxation"],
    "power / utility": ["power distribution", "smart meter", "scada", "electricity", "discom", "tangedco", "energy management", "utility billing"],
    "water / drainage": ["water supply", "drainage", "sewerage", "water management"],
    "port / logistics": ["port", "ports", "maritime", "terminal operating", "logistics", "supply chain", "warehouse management"],
    "banking / finance": ["core banking", "banking", "fintech", "financial services", "insurance", "treasury"],
    "education": ["education", "school", "schools", "university", "learning management", "lms"],
    "surveillance / security systems": ["cctv", "surveillance", "video analytics", "anpr", "access control", "video management"],
    "toll / highways": ["toll", "highway", "highways", "fastag", "road transport", "traffic management"],
    "public distribution": ["ration", "pds", "civil supplies", "public distribution", "fair price shop"],
}

TECH_ALIASES: Dict[str, str] = {
    "postgres": "postgresql", "psql": "postgresql", "mongo": "mongodb", "node": "node", "nodejs": "node",
    "node.js": "node", "reactjs": "react", "react.js": "react", "react js": "react", "vuejs": "vue", "vue.js": "vue",
    "angularjs": "angular", "k8s": "kubernetes", "js": "javascript", "ts": "typescript", "golang": "go",
    "dotnet": ".net", ".net core": ".net", "asp.net core": "asp.net", "ms sql": "sql server", "mssql": "sql server",
    "microsoft sql server": "sql server", "oracle db": "oracle", "oracle database": "oracle", "amazon web services": "aws",
    "ms azure": "azure", "microsoft azure": "azure", "gcp": "google cloud", "ci/cd": "ci/cd", "cicd": "ci/cd",
}


def _pattern(alias: str) -> "re.Pattern[str]":
    return re.compile(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", re.IGNORECASE)


_COMPILED = {name: [_pattern(a) for a in aliases] for name, aliases in DOMAINS.items()}


def _norm(text: str) -> str:
    """Lower-case, one space between words, and the PDF line-wrap 'e- commerce' read as 'e-commerce'."""
    return re.sub(r"(?<=\w)-\s+(?=\w)", "-", " ".join(str(text or "").lower().split()))


def domains_in(text: str) -> List[str]:
    """Domain names the text asks for, in a stable order."""
    t = _norm(text)
    return [name for name, pats in _COMPILED.items() if any(p.search(t) for p in pats)]


def text_has_domain(text: str, domains: Iterable[str]) -> bool:
    t = _norm(text)
    return any(p.search(t) for d in domains for p in _COMPILED.get(d, []))


def canonical_tech(name: str) -> str:
    n = " ".join(str(name or "").lower().split())
    return TECH_ALIASES.get(n, n)
