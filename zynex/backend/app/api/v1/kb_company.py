"""Company master sections of the knowledge base: registrations and identity facts, financial years, OEM partners, offices.

Same access rule as the rest of the knowledge base (everyone reads, admins write). Exact facts only: nothing here is searched
by meaning. A value marked `is_sample` is a placeholder; the eligibility engine asks for confirmation instead of deciding on it.
"""
from datetime import date
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.models.knowledge_base import CompanyOffice, CompanyProfile, OemPartnership
from app.models.project_documents import FinancialRecord

router = APIRouter(prefix="/kb", tags=["knowledge-base"])

YES_NO = ("yes", "no")

# (key, label, kind, hint). kind: text | longtext | date | number | yesno | choice:a|b|c ; one source of truth for the screen and the engine
SECTIONS: List[dict] = [
    {"id": "identity", "title": "Corporate identity", "fields": [
        ("company_legal_name", "Company legal name", "text", ""),
        ("trade_name_short_name", "Trade / brand name", "text", ""),
        ("company_type", "Entity type", "text", "For example Private Limited Company"),
        ("date_of_incorporation", "Date of incorporation", "text", "For example 14 March 2014"),
        ("registered_address", "Registered address", "longtext", ""),
        ("corporate_address", "Corporate office address", "longtext", ""),
        ("corporate_website", "Website", "text", ""),
        ("business_email", "Business e-mail", "text", ""),
        ("business_phone", "Business phone", "text", ""),
        ("authorised_capital", "Authorised capital", "text", ""),
        ("paid_up_capital", "Paid-up capital", "text", ""),
    ]},
    {"id": "registrations", "title": "Statutory and government registrations", "fields": [
        ("cin", "CIN", "text", ""), ("pan", "PAN", "text", ""), ("tan", "TAN", "text", ""),
        ("gstin", "GSTIN", "text", ""), ("gst_filing_status", "GST filing status", "text", ""),
        ("msme_registration", "Udyam / MSME registration", "text", ""),
        ("epf_registration", "EPF registration", "text", ""), ("esi_registration", "ESI registration", "text", ""),
        ("pt_registration_tamil_nadu", "Professional tax registration", "text", ""),
        ("gem_seller_id", "GeM seller ID", "text", ""),
        ("eprocurement_registrations", "e-Procurement registrations", "longtext", "Portals the company is registered on"),
    ]},
    {"id": "msme", "title": "MSME, start-up and local content", "fields": [
        ("msme_category", "MSME category", "choice:Micro Enterprise|Small Enterprise|Medium Enterprise|Not an MSME", ""),
        ("startup_status", "Recognised start-up", "yesno", ""),
        ("mii_class", "Make in India class", "choice:Class-I local supplier|Class-II local supplier|Non-local supplier", ""),
        ("emd_exemption", "Eligible for EMD exemption", "yesno", "Many tenders waive the bid security for MSMEs"),
        ("tender_fee_exemption", "Eligible for tender-fee exemption", "yesno", ""),
    ]},
    {"id": "financial_strength", "title": "Banking and financial strength", "fields": [
        ("bankers", "Bankers", "text", ""),
        ("bank_guarantee_limit", "Bank guarantee limit (INR)", "number", "Largest guarantee the bank will issue"),
        ("existing_bg_exposure", "Guarantees already in use (INR)", "number", ""),
        ("solvency_certificate", "Solvency certificate", "text", ""),
        ("bank_account_number", "Bank account number", "text", "Hidden on screen; never added to the search index"),
        ("ifsc_code", "IFSC code", "text", ""),
    ]},
    {"id": "legal", "title": "Legal and compliance", "fields": [
        ("blacklisted", "Blacklisted by any government agency", "yesno", "Answer yes only if this is true"),
        ("debarred", "Debarred from bidding", "yesno", ""),
        ("insolvency", "Insolvency or liquidation proceedings", "yesno", ""),
        ("litigation_pending", "Litigation or arbitration pending", "yesno", ""),
        ("litigation_details", "Litigation details", "longtext", "Authority, case number and status"),
    ]},
    {"id": "bidding", "title": "Bidding capability", "fields": [
        ("can_bid_as_consortium", "Can bid as a consortium or joint venture", "yesno", ""),
        ("can_be_lead_bidder", "Can act as lead bidder", "yesno", ""),
        ("preferred_partners", "Preferred consortium partners", "longtext", ""),
        ("dsc_available", "Digital signature certificate available", "yesno", ""),
    ]},
    {"id": "standards", "title": "Quality standards on record", "fields": [
        ("iso_9001_2015", "ISO 9001:2015 certificate no.", "text", ""),
        ("iso_27001_2022", "ISO 27001:2022 certificate no.", "text", ""),
        ("cmmi_maturity_level", "CMMI maturity level", "text", ""),
    ]},
]
_KNOWN = {f[0]: f for s in SECTIONS for f in s["fields"]}
_SENSITIVE = {"bank_account_number", "ifsc_code"}


def _mask(v: str) -> str:
    return ("•" * max(len(v) - 4, 4)) + v[-4:]


class ProfileValues(BaseModel):
    values: Dict[str, Optional[str]] = {}
    confirm: List[str] = []          # keep the value as it is, but it is no longer a placeholder


@router.get("/company-profile")
async def get_company_profile(db: AsyncSession = Depends(get_db)):
    rows = {r.key: r for r in (await db.execute(select(CompanyProfile))).scalars()}
    sections = []
    for s in SECTIONS:
        fields = []
        for key, label, kind, hint in s["fields"]:
            r = rows.get(key)
            value = r.value if r else ""
            if r and (r.is_sensitive or key in _SENSITIVE) and value:
                value = _mask(value)
            fields.append({"key": key, "label": label, "kind": kind, "hint": hint, "value": value,
                           "is_sample": bool(r and r.is_sample), "sensitive": key in _SENSITIVE})
        sections.append({"id": s["id"], "title": s["title"], "fields": fields})
    return {"sections": sections}


@router.put("/company-profile")
async def put_company_profile(body: ProfileValues, db: AsyncSession = Depends(get_db)):
    rows = {r.key: r for r in (await db.execute(select(CompanyProfile))).scalars()}
    for key, raw in body.values.items():
        if key not in _KNOWN:
            raise HTTPException(422, f"Unknown field: {key}")
        value = (raw or "").strip()
        kind = _KNOWN[key][2]
        if kind == "yesno" and value and value.lower() not in YES_NO:
            raise HTTPException(422, f"{_KNOWN[key][1]}: answer yes or no")
        if kind == "yesno":
            value = value.lower()
        if kind == "number" and value:
            try:
                float(value.replace(",", ""))
            except ValueError:
                raise HTTPException(422, f"{_KNOWN[key][1]}: enter a number")
            value = value.replace(",", "")
        r = rows.get(key)
        if r and (key in _SENSITIVE or r.is_sensitive) and value == _mask(r.value):
            continue                                   # the masked text came back unchanged
        if not value:
            if r:
                await db.delete(r)
            continue
        if r:
            if r.value != value:
                r.value, r.is_sample = value, False
        else:
            db.add(CompanyProfile(key=key, value=value, is_sensitive=key in _SENSITIVE, is_sample=False))
    for key in body.confirm:
        if key in rows:
            rows[key].is_sample = False
    await db.commit()
    return await get_company_profile(db)


# ── financial years ───────────────────────────────────────────────────────────────────────────────

class FinancialBase(BaseModel):
    fiscal_year: int                 # the year the financial year ENDS: 2024 = FY 2023-24
    annual_turnover: float
    net_profit: Optional[float] = None
    net_worth: Optional[float] = None
    working_capital: Optional[float] = None
    ebitda: Optional[float] = None
    gross_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    current_ratio: Optional[float] = None
    audit_firm: Optional[str] = None
    audit_signoff_date: Optional[date] = None
    notes: Optional[str] = None


class FinancialOut(FinancialBase):
    id: int
    class Config: from_attributes = True


@router.get("/financials", response_model=list[FinancialOut])
async def list_financials(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(FinancialRecord).order_by(FinancialRecord.fiscal_year.desc()))).scalars().all()


@router.post("/financials", response_model=FinancialOut, status_code=201)
async def create_financial(body: FinancialBase, db: AsyncSession = Depends(get_db)):
    if not 1990 <= body.fiscal_year <= 2100:
        raise HTTPException(422, "Enter the year the financial year ends, for example 2025 for FY 2024-25")
    if (await db.execute(select(FinancialRecord).where(FinancialRecord.fiscal_year == body.fiscal_year))).scalar_one_or_none():
        raise HTTPException(409, f"FY {body.fiscal_year - 1}-{str(body.fiscal_year)[2:]} is already recorded; edit it instead")
    obj = FinancialRecord(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.put("/financials/{id}", response_model=FinancialOut)
async def update_financial(id: int, body: FinancialBase, db: AsyncSession = Depends(get_db)):
    obj = (await db.execute(select(FinancialRecord).where(FinancialRecord.id == id))).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Financial year not found")
    clash = (await db.execute(select(FinancialRecord).where(FinancialRecord.fiscal_year == body.fiscal_year, FinancialRecord.id != id))).scalar_one_or_none()
    if clash:
        raise HTTPException(409, "Another record already uses that financial year")
    for k, v in body.model_dump().items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/financials/{id}", status_code=204)
async def delete_financial(id: int, db: AsyncSession = Depends(get_db)):
    obj = (await db.execute(select(FinancialRecord).where(FinancialRecord.id == id))).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Financial year not found")
    await db.delete(obj)
    await db.commit()


# ── OEM partnerships and offices ──────────────────────────────────────────────────────────────────

class OemBase(BaseModel):
    oem: str
    product: Optional[str] = None
    partner_type: Optional[str] = None
    since_year: Optional[int] = None
    status: Optional[str] = None
    territory: Optional[str] = None
    authorization_ref: Optional[str] = None


class OemOut(OemBase):
    id: int
    is_sample: Optional[bool] = None
    class Config: from_attributes = True


class OfficeBase(BaseModel):
    city: str
    state: Optional[str] = None
    office_type: Optional[str] = None
    tenure: Optional[str] = None
    employee_capacity: Optional[int] = None
    address: Optional[str] = None


class OfficeOut(OfficeBase):
    id: int
    is_sample: Optional[bool] = None
    class Config: from_attributes = True


def _crud(path: str, Model, Base, Out, label: str):
    @router.get(f"/{path}", response_model=list[Out], name=f"list_{path}")
    async def _list(db: AsyncSession = Depends(get_db)):
        return (await db.execute(select(Model).order_by(Model.id))).scalars().all()

    @router.post(f"/{path}", response_model=Out, status_code=201, name=f"create_{path}")
    async def _create(body: Base, db: AsyncSession = Depends(get_db)):
        obj = Model(**body.model_dump(), is_sample=False)
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return obj

    @router.put(f"/{path}/{{id}}", response_model=Out, name=f"update_{path}")
    async def _update(id: int, body: Base, db: AsyncSession = Depends(get_db)):
        obj = (await db.execute(select(Model).where(Model.id == id))).scalar_one_or_none()
        if not obj:
            raise HTTPException(404, f"{label} not found")
        for k, v in body.model_dump().items():
            setattr(obj, k, v)
        obj.is_sample = False                  # edited by a person: no longer a placeholder
        await db.commit()
        await db.refresh(obj)
        return obj

    @router.post(f"/{path}/{{id}}/confirm", response_model=Out, name=f"confirm_{path}")
    async def _confirm(id: int, db: AsyncSession = Depends(get_db)):
        obj = (await db.execute(select(Model).where(Model.id == id))).scalar_one_or_none()
        if not obj:
            raise HTTPException(404, f"{label} not found")
        obj.is_sample = False
        await db.commit()
        await db.refresh(obj)
        return obj

    @router.delete(f"/{path}/{{id}}", status_code=204, name=f"delete_{path}")
    async def _delete(id: int, db: AsyncSession = Depends(get_db)):
        obj = (await db.execute(select(Model).where(Model.id == id))).scalar_one_or_none()
        if not obj:
            raise HTTPException(404, f"{label} not found")
        await db.delete(obj)
        await db.commit()


_crud("oem-partnerships", OemPartnership, OemBase, OemOut, "Partnership")
_crud("offices", CompanyOffice, OfficeBase, OfficeOut, "Office")
