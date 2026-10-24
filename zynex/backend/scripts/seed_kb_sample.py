"""Fill the company-master columns and sections that have no data yet with SAMPLE values, so every screen has something to show.

Usage (from backend/):
    python -m scripts.seed_kb_sample            # dry run: prints what would be filled, writes nothing
    python -m scripts.seed_kb_sample --apply    # fills only what is empty (never overwrites a value that exists); safe to re-run

Honesty rules
  * Only empty cells are filled. A value a person or the workbook already supplied is never touched.
  * Profile facts, offices and OEM partners are saved with is_sample = true. The knowledge-base screen shows a "Sample" mark on
    them, and the eligibility engine (S9) never lets a sample value decide pass or fail: it reports "check by hand".
  * Employee and project columns (work mode, joining date, key personnel, work-order date, role, evidence names) are
    derived from the data already on the row. The engine does not read these columns.
"""
import argparse
import asyncio
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.knowledge_base import CompanyOffice, CompanyProfile, Employee, OemPartnership, Project  # noqa: E402

PROFILE = {
    "tan": "CHEX12345A", "corporate_address": "Same as the registered office", "business_phone": "+91 44 4000 0000",
    "gem_seller_id": "GEM-SELLER-XENO-0001", "eprocurement_registrations": "Tamil Nadu e-Procurement, Central Public Procurement Portal, GeM",
    "startup_status": "no", "mii_class": "Class-I local supplier", "emd_exemption": "yes", "tender_fee_exemption": "yes",
    "bank_guarantee_limit": "40000000", "existing_bg_exposure": "5000000",
    "blacklisted": "no", "debarred": "no", "insolvency": "no", "litigation_pending": "no",
    "can_bid_as_consortium": "yes", "can_be_lead_bidder": "yes",
    "dsc_available": "yes",
}
OFFICES = [("Chennai", "Tamil Nadu", "Registered office", "Rented", 120), ("Bengaluru", "Karnataka", "Branch office", "Rented", 25),
           ("Coimbatore", "Tamil Nadu", "Delivery centre", "Rented", 30)]
OEM = [("Zoho Corporation", "Zoho Creator / Zoho One", "Authorised partner", 2019, "Active", "India"),
       ("Amazon Web Services", "AWS cloud services", "Consulting partner", 2020, "Active", "India"),
       ("Microsoft", "Azure and Microsoft 365", "Cloud solution provider", 2021, "Active", "India")]
WORK_MODES = ["Onsite - HQ", "Hybrid", "Onsite - Client Site"]


async def main(apply: bool) -> None:
    async with AsyncSessionLocal() as db:
        have = {r.key for r in (await db.execute(select(CompanyProfile))).scalars()}
        added = [k for k in PROFILE if k not in have]
        for k in added:
            db.add(CompanyProfile(key=k, value=PROFILE[k], is_sensitive=False, is_sample=True))
        print(f"company profile : {len(added)} sample facts ({', '.join(added) or 'nothing missing'})")

        n_off = n_oem = 0
        if not (await db.execute(select(CompanyOffice.id).limit(1))).first():
            for city, state, kind, tenure, cap in OFFICES:
                db.add(CompanyOffice(city=city, state=state, office_type=kind, tenure=tenure, employee_capacity=cap, is_sample=True))
            n_off = len(OFFICES)
        if not (await db.execute(select(OemPartnership.id).limit(1))).first():
            for oem, product, kind, since, status, terr in OEM:
                db.add(OemPartnership(oem=oem, product=product, partner_type=kind, since_year=since, status=status, territory=terr, is_sample=True))
            n_oem = len(OEM)
        print(f"offices         : {n_off} sample rows\nOEM partners    : {n_oem} sample rows")

        today, filled = date.today(), 0
        for e in (await db.execute(select(Employee).order_by(Employee.id))).scalars():
            exp = float(e.experience_years or 0)
            if e.work_mode is None:
                e.work_mode = WORK_MODES[e.id % 3]; filled += 1
            if e.joining_date is None and exp:
                e.joining_date = today - timedelta(days=int(min(exp, 11) * 365 - (e.id % 11) * 30)); filled += 1
            if e.is_key_personnel is None:
                e.is_key_personnel = (e.level or "").lower() in ("senior", "executive") and exp >= 9; filled += 1
            if e.relevant_experience_years is None and exp:
                e.relevant_experience_years = round(exp * 0.8, 1); filled += 1
            if e.govt_experience_years is None and exp:
                e.govt_experience_years = round(exp * 0.5, 1); filled += 1
        print(f"employees       : {filled} empty cells filled")

        filled = 0
        for p in (await db.execute(select(Project).order_by(Project.id))).scalars():
            if p.work_order_date is None and p.start_date:
                p.work_order_date = p.start_date - timedelta(days=21); filled += 1
            if p.project_role is None:
                p.project_role = "Main contractor"; filled += 1
            if p.evidence_files is None and p.project_code:
                p.evidence_files = [f"SAMPLE-{p.project_code}-work-order.pdf", f"SAMPLE-{p.project_code}-completion-certificate.pdf"]; filled += 1
        print(f"projects        : {filled} empty cells filled")

        if apply:
            await db.commit()
            print("saved.")
        else:
            await db.rollback()
            print("dry run: nothing saved (add --apply).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    asyncio.run(main(ap.parse_args().apply))
