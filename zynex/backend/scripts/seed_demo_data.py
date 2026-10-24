"""Insert fictional demo data into the knowledge base (clients, projects, employees, technologies, certifications).

FOR LOCAL DEVELOPMENT ONLY. Never run this against a real server database.
Usage (from backend/):  python -m scripts.seed_demo_data
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.knowledge_base import Certification, Client, Employee, Project, Technology  # noqa: E402


async def main() -> None:
    async with AsyncSessionLocal() as db:
        if (await db.execute(select(Technology).limit(1))).scalar_one_or_none() is not None:
            print("Demo data already seeded; skipping.")
            return
        # Clients
        clients_data = [
            Client(name="Dubai Roads & Transport Authority", industry="Government / Transport", country="UAE", contact_email="it@rta.ae", notes="AFC & ticketing system integrator"),
            Client(name="Kerala State Road Transport Corp", industry="Government / Transport", country="India", contact_email="it@ksrtc.kerala.gov.in", notes="Fleet & GPS tracking"),
            Client(name="Oman National Transport Company", industry="Transport & Logistics", country="Oman", contact_email="tech@ontc.om", notes="Passenger AFC solution"),
            Client(name="Lulu Hypermarket Group", industry="Retail", country="UAE", contact_email="tech@luluhyper.com", notes="Retail ERP & analytics"),
            Client(name="Gulf Petrochem Group", industry="Oil & Gas", country="UAE", contact_email="it@gulfpetro.ae", notes="Enterprise ERP"),
            Client(name="Kerala State IT Mission", industry="Government / e-Governance", country="India", contact_email="contact@itmission.kerala.gov.in", notes="Citizen services portal"),
        ]
        for c in clients_data:
            db.add(c)
        await db.flush()

        # Projects
        projects_data = [
            Project(name="Automated Fare Collection (AFC) – RTA Dubai", client_id=clients_data[0].id,
                    description="End-to-end AFC system for metro and bus network covering smart card issuance, top-up kiosks, gate controllers, back-office settlement, and revenue reporting. Integrated with NOL card ecosystem.",
                    technologies=["Java", "Spring Boot", "Angular", ".NET", "SQL Server", "Redis", "ISO 14443"],
                    team_size=18, duration_weeks=52, total_value=12500000.0, status="completed"),
            Project(name="GPS Fleet Tracking & AVLS – KSRTC", client_id=clients_data[1].id,
                    description="Automatic Vehicle Location System with real-time GPS tracking, schedule adherence monitoring, driver behavior analytics, and passenger information displays at bus stops.",
                    technologies=["Python", "FastAPI", "React", "PostgreSQL", "MQTT", "GPS/GNSS", "Android", "Flutter"],
                    team_size=10, duration_weeks=32, total_value=3800000.0, status="completed"),
            Project(name="Ticketing & Passenger Management – ONTC", client_id=clients_data[2].id,
                    description="Integrated bus ticketing platform with mobile app (iOS & Android), web portal, handheld ticket validators, and back-office management with ridership analytics.",
                    technologies=["Flutter", "iOS (Swift)", "Android (Kotlin)", "Node.js", "PostgreSQL", "React", "Docker"],
                    team_size=12, duration_weeks=36, total_value=5200000.0, status="completed"),
            Project(name="Retail ERP & POS System – Lulu Hypermarket", client_id=clients_data[3].id,
                    description="Multi-branch retail ERP covering inventory management, POS billing, supplier management, loyalty program, and real-time sales analytics dashboard.",
                    technologies=[".NET", "Angular", "SQL Server", "PHP", "WooCommerce", "Power BI", "Docker"],
                    team_size=14, duration_weeks=44, total_value=7600000.0, status="completed"),
            Project(name="Enterprise ERP – Gulf Petrochem", client_id=clients_data[4].id,
                    description="Full-scale ERP covering finance, HR, supply chain, procurement, and asset management. Integrated with existing SAP modules.",
                    technologies=["Java", "Spring Boot", "React", "PostgreSQL", "Docker", "Kubernetes"],
                    team_size=15, duration_weeks=48, total_value=9800000.0, status="completed"),
            Project(name="e-Governance Citizen Portal – Kerala IT Mission", client_id=clients_data[5].id,
                    description="Unified citizen services portal with online applications, document verification, grievance management, and real-time status tracking for 200+ government services.",
                    technologies=["React", "Python", "Django", "PostgreSQL", "Redis", "Android", "iOS (Swift)"],
                    team_size=9, duration_weeks=30, total_value=4100000.0, status="completed"),
            Project(name="ZYNEX – AI Estimation Platform (Internal)", client_id=clients_data[0].id,
                    description="AI-powered tender and project estimation platform. Processes RFPs, SRS documents, generates cost estimates, evaluates tender eligibility, and auto-generates proposal documents.",
                    technologies=["Python", "FastAPI", "React", "TypeScript", "PostgreSQL", "Ollama", "Docker"],
                    team_size=4, duration_weeks=24, total_value=900000.0, status="active"),
        ]
        for p in projects_data:
            db.add(p)
        await db.flush()

        # Employees
        employees_data = [
            Employee(name="Arjun Menon", role="Full Stack Developer", level="senior", skills=["React", "Angular", "Python", "FastAPI", "PostgreSQL", "TypeScript"], hourly_rate=2500.0, is_active=True),
            Employee(name="Priya Nair", role="UI/UX Designer", level="mid", skills=["Figma", "Adobe XD", "React", "Flutter UI", "Tailwind CSS"], hourly_rate=1800.0, is_active=True),
            Employee(name="Mohammed Al-Rashid", role="DevOps / Cloud Engineer", level="senior", skills=["Docker", "Kubernetes", "CI/CD", "AWS", "Azure", "Linux"], hourly_rate=2800.0, is_active=True),
            Employee(name="Sneha Pillai", role="QA Engineer", level="mid", skills=["Selenium", "Pytest", "Postman", "JIRA", "Appium", "Manual Testing"], hourly_rate=1600.0, is_active=True),
            Employee(name="Rahul Sharma", role=".NET Developer", level="mid", skills=[".NET", "C#", "ASP.NET Core", "SQL Server", "Angular"], hourly_rate=2000.0, is_active=True),
            Employee(name="Aisha Khalid", role="Business Analyst", level="senior", skills=["Requirements Analysis", "BPMN", "UAT", "Transport Domain", "AFC Systems"], hourly_rate=2200.0, is_active=True),
            Employee(name="Thomas George", role="Project Manager", level="senior", skills=["Agile", "Scrum", "PMP", "Stakeholder Management", "MS Project"], hourly_rate=3000.0, is_active=True),
            Employee(name="Nisha Varghese", role="Mobile Developer", level="mid", skills=["Flutter", "Dart", "Android (Kotlin)", "iOS (Swift)", "Firebase"], hourly_rate=2100.0, is_active=True),
            Employee(name="Sanjay Krishnan", role="Java Developer", level="senior", skills=["Java", "Spring Boot", "Hibernate", "Microservices", "Kafka"], hourly_rate=2600.0, is_active=True),
            Employee(name="Fathima Beevi", role="PHP Developer", level="mid", skills=["PHP", "Laravel", "MySQL", "WordPress", "REST APIs"], hourly_rate=1700.0, is_active=True),
            Employee(name="Deepak Pillai", role="Embedded / Hardware Integration", level="senior", skills=["GPS/GNSS", "RFID", "AFC Hardware", "C++", "Python", "MQTT"], hourly_rate=2400.0, is_active=True),
            Employee(name="Anisha Thomas", role="Data Engineer", level="mid", skills=["Python", "Pandas", "Power BI", "PostgreSQL", "ETL", "Apache Kafka"], hourly_rate=2000.0, is_active=True),
        ]
        for e in employees_data:
            db.add(e)

        # Technologies
        tech_data = [
            Technology(name="React", category="Frontend", proficiency="expert"),
            Technology(name="Angular", category="Frontend", proficiency="expert"),
            Technology(name="TypeScript", category="Frontend", proficiency="advanced"),
            Technology(name="Flutter", category="Mobile", proficiency="advanced"),
            Technology(name="Android (Kotlin)", category="Mobile", proficiency="advanced"),
            Technology(name="iOS (Swift)", category="Mobile", proficiency="intermediate"),
            Technology(name="Python", category="Backend", proficiency="expert"),
            Technology(name="FastAPI", category="Backend", proficiency="expert"),
            Technology(name="Java", category="Backend", proficiency="expert"),
            Technology(name="Spring Boot", category="Backend", proficiency="expert"),
            Technology(name=".NET / C#", category="Backend", proficiency="advanced"),
            Technology(name="PHP / Laravel", category="Backend", proficiency="advanced"),
            Technology(name="Node.js", category="Backend", proficiency="advanced"),
            Technology(name="PostgreSQL", category="Database", proficiency="expert"),
            Technology(name="SQL Server", category="Database", proficiency="advanced"),
            Technology(name="MySQL", category="Database", proficiency="advanced"),
            Technology(name="Redis", category="Cache / Messaging", proficiency="advanced"),
            Technology(name="Apache Kafka", category="Messaging", proficiency="intermediate"),
            Technology(name="Docker", category="DevOps", proficiency="expert"),
            Technology(name="Kubernetes", category="DevOps", proficiency="intermediate"),
            Technology(name="GPS / GNSS Integration", category="Hardware / IoT", proficiency="advanced"),
            Technology(name="AFC / Smart Card (ISO 14443)", category="Ticketing", proficiency="advanced"),
            Technology(name="RFID & NFC", category="Hardware / IoT", proficiency="intermediate"),
            Technology(name="Power BI", category="Analytics", proficiency="advanced"),
        ]
        for t in tech_data:
            db.add(t)

        # Certifications
        cert_data = [
            Certification(name="ISO 9001:2015 Quality Management System", issuing_body="Bureau Veritas", certificate_number="BV-QMS-2024-001", valid_until="2026-12-31"),
            Certification(name="ISO 27001:2022 Information Security Management", issuing_body="BSI Group", certificate_number="BSI-ISMS-2024-XNV", valid_until="2027-03-31"),
            Certification(name="CMMI Level 3 Development Appraisal", issuing_body="ISACA", certificate_number="CMMI-L3-2024-XNV", valid_until="2027-06-30"),
            Certification(name="Microsoft Gold Partner – Application Development", issuing_body="Microsoft", certificate_number="MS-GOLD-APPDEV-2024", valid_until="2025-12-31"),
            Certification(name="AWS Certified Solutions Architect – Professional", issuing_body="Amazon Web Services", certificate_number="AWS-SAP-C02-2024", valid_until="2027-03-15"),
            Certification(name="PCI DSS Level 1 Compliance (Payment Card Industry)", issuing_body="Qualified Security Assessor", certificate_number="PCI-L1-2024-XNV", valid_until="2025-09-30"),
        ]
        for c in cert_data:
            db.add(c)

        await db.commit()
        print(f"seeded: {len(clients_data)} clients, {len(projects_data)} projects, {len(employees_data)} employees, "
              f"{len(tech_data)} technologies, {len(cert_data)} certifications")


if __name__ == "__main__":
    asyncio.run(main())
