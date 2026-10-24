"""Fill the company profile, financial years, offices and OEM partners of a FICTIONAL demo company ("Demo Technologies").

FOR LOCAL DEVELOPMENT AND TESTING ONLY. A fresh install has no company records, so every tender requirement would read "no company data".
This gives the tender check something to compare with. It runs only when the company profile is empty, so it never touches real data
(an imported company workbook, or facts a person has saved on the Knowledge Base page).

Usage (from backend/):  python -m scripts.seed_demo_company
Every value below is made up: the PAN, GSTIN, CIN, addresses and figures do not belong to any real organisation.
"""
import asyncio
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.knowledge_base import CompanyOffice, CompanyProfile, OemPartnership  # noqa: E402
from app.models.project_documents import FinancialRecord  # noqa: E402

CR = 1e7
PROFILE = {
    "company_legal_name": "Demo Technologies Private Limited", "trade_name_short_name": "Demo Technologies", "company_type": "Private Limited Company",
    "date_of_incorporation": "01 April 2015", "registered_address": "Plot 1, Demo Industrial Estate, Chennai - 600 001, Tamil Nadu",
    "corporate_website": "https://www.demo-technologies.example", "business_email": "tenders@demo-technologies.example",
    "cin": "U00000TN2015PTC000000", "pan": "AAAAA0000A", "tan": "AAAA00000A", "gstin": "33AAAAA0000A1Z5", "gst_filing_status": "Regular filer",
    "msme_registration": "UDYAM-TN-00-0000000", "msme_category": "Small Enterprise", "epf_registration": "TNMAS0000000000",
    "esi_registration": "00000000000000000", "startup_status": "no", "emd_exemption": "yes",
    "bank_guarantee_limit": "30000000", "blacklisted": "no", "debarred": "no", "insolvency": "no", "litigation_pending": "no",
    "can_bid_as_consortium": "no", "can_be_lead_bidder": "no", "dsc_available": "yes",
    "iso_9001_2015": "DEMO-ISO9001-0001", "iso_27001_2022": "DEMO-ISO27001-0001", "cmmi_maturity_level": "Level 3",
}
FINANCIALS = {2022: (18.0, 2.1, 6.0, 4.0), 2023: (22.5, 2.9, 8.5, 5.5), 2024: (27.0, 3.4, 11.0, 7.0), 2025: (31.5, 4.0, 14.5, 9.0), 2026: (36.0, 4.6, 18.0, 11.0)}
OFFICES = [("Chennai", "Tamil Nadu", "Registered office", "Owned", 80), ("Bengaluru", "Karnataka", "Branch office", "Rented", 20)]
OEM = [("Demo Cloud Provider", "Cloud platform", "Authorised partner", 2020, "Active", "India")]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        if (await db.execute(select(CompanyProfile).limit(1))).scalar_one_or_none() is not None:
            print("A company profile already exists; the demo company was not added.")
            return
        for k, v in PROFILE.items():
            db.add(CompanyProfile(key=k, value=v, is_sensitive=False, is_sample=False))
        have = {r.fiscal_year for r in (await db.execute(select(FinancialRecord))).scalars()}
        for fy, (turnover, profit, worth, wc) in FINANCIALS.items():
            if fy not in have:
                db.add(FinancialRecord(fiscal_year=fy, annual_turnover=turnover * CR, net_profit=profit * CR, net_worth=worth * CR,
                                       working_capital=wc * CR, currency="INR", audit_firm="Demo & Associates, Chartered Accountants",
                                       audit_signoff_date=date(fy, 7, 30)))
        for city, state, kind, tenure, cap in OFFICES:
            db.add(CompanyOffice(city=city, state=state, office_type=kind, tenure=tenure, employee_capacity=cap, is_sample=False))
        for oem, product, kind, since, status, terr in OEM:
            db.add(OemPartnership(oem=oem, product=product, partner_type=kind, since_year=since, status=status, territory=terr, is_sample=False))
        await db.commit()
        print(f"Demo company added: {len(PROFILE)} facts, {len(FINANCIALS)} financial years, {len(OFFICES)} offices, {len(OEM)} OEM partner.")


if __name__ == "__main__":
    asyncio.run(main())
