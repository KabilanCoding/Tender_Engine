"""Seed Xenovex Technologies (Ekkatuthangal) Knowledge Base into ZYNEX PostgreSQL.

Reads the approved dataset from 'xenovex_knowledge_base_tender_data_FINAL.xlsx'
and populates financial_records, certifications, projects, clients, employees, and technologies.

Run only after senior approval:
    backend/.venv/bin/python -m scripts.seed_xenovex_kb
"""
import asyncio
import os
import sys
from datetime import datetime, date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select, text
from app.core.database import AsyncSessionLocal
from app.models.knowledge_base import Certification, Client, Employee, Project, Technology
from app.models.project_documents import FinancialRecord
import openpyxl


def parse_date(v):
    if not v:
        return None
    if isinstance(v, (datetime, date)):
        return v if isinstance(v, date) else v.date()
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


async def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    excel_path = os.path.join(root_dir, "xenovex_knowledge_base_tender_data_FINAL.xlsx")
    
    if not os.path.exists(excel_path):
        print(f"Error: {excel_path} not found.")
        sys.exit(1)

    print(f"Loading approved Xenovex knowledge base from {excel_path}...")
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    
    async with AsyncSessionLocal() as db:
        # 1. Financial Records
        ws_fin = wb["02_Financial_Records"]
        existing_fy = set((await db.execute(select(FinancialRecord.fiscal_year))).scalars())
        added_fin = 0
        for row in list(ws_fin.iter_rows(values_only=True))[4:9]:
            if not row or not row[1]:
                continue
            fy = int(row[1])
            if fy not in existing_fy:
                fr = FinancialRecord(
                    fiscal_year=fy,
                    annual_turnover=float(row[2]),
                    net_profit=float(row[4]) if row[4] else None,
                    currency="INR",
                    notes=f"{row[0]} Audited. UDIN: {row[9]}"
                )
                db.add(fr)
                added_fin += 1
        print(f"✓ Added {added_fin} Financial Records (FY 2019-20 to FY 2023-24).")

        # 2. Certifications
        ws_cert = wb["03_Certifications"]
        existing_certs = set((await db.execute(select(Certification.name))).scalars())
        added_certs = 0
        for row in list(ws_cert.iter_rows(values_only=True))[4:]:
            if not row or not row[0]:
                continue
            name = str(row[0]).strip()
            if name not in existing_certs:
                c = Certification(
                    name=name,
                    valid_until=str(row[6]) if row[6] else None
                )
                db.add(c)
                added_certs += 1
        print(f"✓ Added {added_certs} Certifications (ISO 9001, 27001, 20000, CMMI L5, etc).")

        # 3. Clients
        ws_cli = wb["06_Clients_Directory"]
        existing_clients = {c.name: c.id for c in (await db.execute(select(Client))).scalars()}
        added_clients = 0
        for row in list(ws_cli.iter_rows(values_only=True))[4:]:
            if not row or not row[1]:
                continue
            cname = str(row[1]).strip()
            if cname not in existing_clients:
                cl = Client(
                    name=cname,
                    industry=str(row[2]),
                    country=str(row[3]),
                    contact_email=str(row[6]),
                    notes=str(row[7])
                )
                db.add(cl)
                await db.flush()
                existing_clients[cname] = cl.id
                added_clients += 1
        print(f"✓ Added {added_clients} Client profiles.")

        # 4. Past Projects
        ws_proj = wb["04_Past_Projects"]
        existing_projects = set((await db.execute(select(Project.name))).scalars())
        added_proj = 0
        for row in list(ws_proj.iter_rows(values_only=True))[4:]:
            if not row or not row[1]:
                continue
            pname = str(row[1]).strip()
            if pname not in existing_projects:
                client_id = existing_clients.get(str(row[2]).strip())
                techs = [t.strip() for t in str(row[11]).split(",") if t.strip()]
                pr = Project(
                    name=pname,
                    client_id=client_id,
                    description=str(row[12]),
                    status=str(row[6]).lower(),
                    duration_weeks=int(row[9]) if row[9] else None,
                    team_size=int(row[10]) if row[10] else None,
                    total_value=float(row[4]) if row[4] else None,
                    technologies=techs
                )
                db.add(pr)
                added_proj += 1
        print(f"✓ Added {added_proj} Past Projects (up to ₹38.5 Cr).")

        # 5. Employees
        ws_emp = wb["05_Employees_Key_Personnel"]
        existing_emps = set((await db.execute(select(Employee.name))).scalars())
        added_emps = 0
        for row in list(ws_emp.iter_rows(values_only=True))[4:]:
            if not row or not row[1]:
                continue
            ename = str(row[1]).strip()
            if ename not in existing_emps:
                skills = [s.strip() for s in str(row[8]).split(",") if s.strip()]
                em = Employee(
                    name=ename,
                    email=f"{ename.lower().replace(' ', '.')}@xenovex.com",
                    role=str(row[2]),
                    level=str(row[3]).lower(),
                    skills=skills,
                    is_active=True
                )
                db.add(em)
                added_emps += 1
        print(f"✓ Added {added_emps} Active Employees (bringing total technical headcount to 55+).")

        # 6. Technology Taxonomy
        ws_tech = wb["07_Technology_Taxonomy"]
        existing_techs = set((await db.execute(select(Technology.name))).scalars())
        added_tech = 0
        for row in list(ws_tech.iter_rows(values_only=True))[4:]:
            if not row or not row[0]:
                continue
            tname = str(row[0]).strip()
            if tname not in existing_techs:
                t = Technology(
                    name=tname,
                    category=str(row[2])
                )
                db.add(t)
                added_tech += 1
        print(f"✓ Added {added_tech} Technologies.")

        await db.commit()
        print("\n🎉 Xenovex Knowledge Base fully synced to database!")

if __name__ == "__main__":
    asyncio.run(main())
