"""Company facts assembled from the zynex knowledge base for eligibility evaluation.

Rule: a fact the knowledge base does not hold is None/empty ("unknown"). It is never defaulted,
so the rule engine reports MISSING instead of inventing a PASS.
"""
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_base import Certification, Client, CompanyOffice, CompanyProfile, Employee, OemPartnership, Project, Technology
from app.models.project_documents import FinancialRecord
from app.services.eligibility.normalizer import Normalizer


@dataclass
class CertFact:
    name: str
    valid_until: Optional[date] = None   # None = validity date not recorded
    raw_valid_until: str = ""             # what was stored, for messages

    @property
    def validity_unreadable(self) -> bool:
        """A validity date was entered but cannot be read: never treat that as 'valid'."""
        return self.valid_until is None and bool(self.raw_valid_until.strip())

    def is_expired(self, today: Optional[date] = None) -> bool:
        return self.valid_until is not None and self.valid_until < (today or date.today())


@dataclass
class ProjectFact:
    name: str
    value: Optional[float]
    status: str
    technologies: List[str] = field(default_factory=list)
    description: str = ""
    client: str = ""
    industry: str = ""
    duration_weeks: Optional[int] = None
    team_size: Optional[int] = None
    completion_date: Optional[date] = None
    start_date: Optional[date] = None
    domain: str = ""
    client_type: str = ""

    @property
    def searchable_text(self) -> str:
        """Everything the knowledge base says about what this project was (for domain matching)."""
        return " ".join([self.name, self.description, self.industry, self.domain, " ".join(self.technologies)]).lower()

    @property
    def is_government_client(self) -> Optional[bool]:
        """True/False when the client type is recorded, None when it is not."""
        text = f"{self.client_type} {self.industry}".lower()
        if not text.strip():
            return None
        return bool(re.search(r"government|govt|\bpsu\b|public sector|ministry|municipal|smart city", text))


@dataclass
class EmployeeFact:
    name: str
    role: str = ""
    level: str = ""
    skills: List[str] = field(default_factory=list)
    experience_years: Optional[float] = None
    qualification: str = ""
    professional_certifications: str = ""
    department: str = ""

    @property
    def profile_text(self) -> str:
        """Everything recorded about what this person does, for matching a required role."""
        return " ".join([self.role, self.department, " ".join(self.skills)]).lower()       # not certificates: a PMP holder is not a project manager


@dataclass
class OfficeFact:
    city: str
    state: str = ""
    office_type: str = ""
    is_sample: bool = False


@dataclass
class OemFact:
    oem: str
    product: str = ""
    partner_type: str = ""
    status: str = ""
    territory: str = ""
    is_sample: bool = False


@dataclass
class CompanyFacts:
    # key = END year of the Indian financial year: 2024 means FY 2023-24 (April 2023 - March 2024)
    turnover_by_fy: Dict[int, float] = field(default_factory=dict)
    net_worth_by_fy: Dict[int, float] = field(default_factory=dict)
    working_capital_by_fy: Dict[int, float] = field(default_factory=dict)
    net_profit_by_fy: Dict[int, float] = field(default_factory=dict)
    profile: Dict[str, str] = field(default_factory=dict)       # GSTIN, PAN, address ... (company_profile table)
    profile_sample: Set[str] = field(default_factory=set)       # profile keys whose value is a placeholder, not a confirmed fact
    offices: List[OfficeFact] = field(default_factory=list)
    oem_partners: List[OemFact] = field(default_factory=list)
    certifications: List[CertFact] = field(default_factory=list)
    employee_count: Optional[int] = None   # None = no employee records at all
    projects: List[ProjectFact] = field(default_factory=list)
    technologies: Set[str] = field(default_factory=set)
    employees: List[EmployeeFact] = field(default_factory=list)

    @property
    def completed_projects(self) -> List[ProjectFact]:
        return [p for p in self.projects if (p.status or "").strip().lower() == "completed"]

    @property
    def has_any_data(self) -> bool:
        return bool(self.turnover_by_fy or self.certifications or self.employee_count
                    or self.projects or self.technologies)

    def summary(self) -> Dict[str, int]:
        return {
            "financial_years": len(self.turnover_by_fy),
            "certifications": len(self.certifications),
            "employees": self.employee_count or 0,
            "projects": len(self.projects),
            "technologies": len(self.technologies),
        }


class CompanyFactsProvider:
    @staticmethod
    async def load(db: AsyncSession) -> CompanyFacts:
        facts = CompanyFacts()

        for fr in (await db.execute(select(FinancialRecord))).scalars():
            fy = int(fr.fiscal_year)
            facts.turnover_by_fy[fy] = float(fr.annual_turnover)
            if fr.net_worth is not None:
                facts.net_worth_by_fy[fy] = float(fr.net_worth)
            if fr.working_capital is not None:
                facts.working_capital_by_fy[fy] = float(fr.working_capital)
            if fr.net_profit is not None:
                facts.net_profit_by_fy[fy] = float(fr.net_profit)

        for pr in (await db.execute(select(CompanyProfile))).scalars():
            facts.profile[pr.key] = pr.value
            if pr.is_sample:
                facts.profile_sample.add(pr.key)

        for o in (await db.execute(select(CompanyOffice))).scalars():
            facts.offices.append(OfficeFact(o.city or "", o.state or "", o.office_type or "", bool(o.is_sample)))
        for m in (await db.execute(select(OemPartnership))).scalars():
            facts.oem_partners.append(OemFact(m.oem or "", m.product or "", m.partner_type or "", m.status or "",
                                              m.territory or "", bool(m.is_sample)))

        for c in (await db.execute(select(Certification))).scalars():
            facts.certifications.append(CertFact(name=c.name, valid_until=c.valid_until_date or Normalizer.parse_date(c.valid_until),
                                                 raw_valid_until=str(c.valid_until or "")))

        employees = list((await db.execute(select(Employee).where(Employee.is_active.is_(True)))).scalars())
        facts.employee_count = len(employees) or None
        for e in employees:
            skills = [str(s).strip() for s in (e.skills or []) if str(s).strip()]
            facts.technologies.update(x.lower() for x in skills)
            facts.employees.append(EmployeeFact(e.name, e.role or "", e.level or "", skills, e.experience_years,
                                                e.qualification or "", e.professional_certifications or "",
                                                e.department or ""))

        clients = {c.id: c for c in (await db.execute(select(Client))).scalars()}
        for p in (await db.execute(select(Project))).scalars():
            techs = [str(t).strip() for t in (p.technologies or []) if str(t).strip()]
            cl = clients.get(p.client_id)
            facts.projects.append(ProjectFact(p.name, p.total_value, p.status or "", techs,
                                              description=p.description or "", client=(cl.name if cl else ""),
                                              industry=(cl.industry or "") if cl else "",
                                              duration_weeks=p.duration_weeks, team_size=p.team_size,
                                              completion_date=p.completion_date, start_date=p.start_date,
                                              domain=p.domain or "", client_type=(cl.client_type or "") if cl else ""))
            facts.technologies.update(t.lower() for t in techs)

        for t in (await db.execute(select(Technology))).scalars():
            facts.technologies.add(t.name.strip().lower())
        return facts
