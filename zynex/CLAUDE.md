



\# Application Manifest – Local AI Tender \& Estimation Platform called -  ZYNEX



\## 1. Application Name



\*\*ZYNEX\*\*



ZYNEX = Zero-Cloud, Your-Data, Neural Estimation \& eXecution



\---



\## 2. Core Objective



Build a \*\*fully local, offline-capable AI platform\*\* that can:



1\. Read and understand requirement documents (SRS, RFP, tender)

2\. Automatically generate project plans and cost estimates

3\. Evaluate company eligibility for tenders

4\. Generate complete tender submission documents

5\. Operate entirely within a secure local environment without external API calls



\---



\## 3. Deployment Constraints



\* Must run on \*\*local machine or on-premise server\*\*

\* No cloud dependencies

\* All AI models must run locally

\* Must support confidential enterprise data

\* Must be deployable on a plain Linux server (systemd + nginx); Docker is not required



\---



\## 4. Core Functional Modules



\### 4.1 Document Understanding Engine



Input formats:



\* PDF

\* DOCX

\* TXT



Responsibilities:



\* Extract text

\* Detect document type (SRS / Tender / Proposal)

\* Identify sections and headings

\* Provide structured output



\---



\### 4.2 Project Estimation Engine



Given an SRS or requirement document, the system should:



1\. Identify functional modules

2\. Break modules into user stories

3\. Generate sprint plan

4\. Estimate effort per task

5\. Calculate total project duration



Outputs:



\* Module breakdown

\* Sprint plan

\* Task list

\* Effort estimation in hours and weeks



\---



\### 4.3 Resource \& Cost Estimation Engine



The system must calculate:



\* Developer effort cost

\* QA cost

\* DevOps cost

\* Infrastructure cost

\* Storage cost

\* Contingency buffer

\* Profit margin



Final output:



\* Total project cost

\* Suggested bid value



\---



\### 4.4 Tender Eligibility Engine



Given a tender document, the system must:



1\. Extract eligibility criteria

2\. Compare criteria with company data

3\. Detect missing or invalid documents

4\. Determine eligibility status



Outputs:



\* Eligibility report

\* Missing documents list

\* Compliance matrix



\---



\### 4.5 Tender Proposal Generator



If eligible, the system should generate:



\* Technical proposal

\* Commercial proposal

\* Company profile

\* Project references

\* Annexures and compliance tables



All generated documents must be exportable as:



\* DOCX

\* PDF



\---



\## 5. Company Knowledge Base



The application must maintain a structured internal database containing:



\### Entities



\* Projects

\* Clients

\* Employees

\* Technologies

\* Certifications

\* Financial records

\* Past tenders

\* Documents



This knowledge base must be queryable by all AI modules.



\---



\## 6. Suggested Technology Stack



\### Backend



\* Python

\* FastAPI



\### Frontend



\* React



\### Database



\* PostgreSQL for structured data



\### Local AI Runtime



\* Ollama



\### Document Parsing



\* PyMuPDF and python-docx (PDF / DOCX text extraction)

\* Tesseract (for OCR)



\---



\## 7. Data Flow Overview



1\. User uploads document

2\. System detects document type

3\. Document is parsed and structured

4\. Appropriate AI engine is invoked

5\. Results are stored and displayed in dashboard



\---



\## 8. Security Requirements



\* Role-based access control

\* Local authentication

\* Encrypted storage for sensitive documents

\* No external network calls



\---



\## 9. Required User Interfaces



\### Admin Panel



\* Manage company knowledge base

\* Upload and validate documents

\* Maintain cost parameters and salary structures



\### Analyst Panel



\* Upload SRS or tender

\* View estimation reports

\* Generate proposals



\---



\## 10. Output Artifacts



The system must be capable of generating:



\* Project estimation reports

\* Commercial cost sheets

\* Tender eligibility reports

\* Complete proposal documents



\---



\## 11. Non-Functional Requirements



\* Must support documents up to 1000 pages

\* Must handle at least 500 internal project records

\* Must be modular and extensible

\* All services must expose REST APIs



\---



\## 12. Development Requirements for Generated Code



The generated application must:



\* Follow layered architecture

\* Separate AI processing from business logic

\* Keep only bootstrap configuration in the environment file; all other application settings are managed on the Settings page (stored in the database)

\* Include server deployment files (systemd unit, nginx site, backup script) instead of Docker

\* Provide database migration scripts



\---



\## 13. Expected Folder Structure



/backend    (FastAPI: app/ with api, services, ai, models, schemas, parsers; migrations; scripts; tests)

/frontend   (React web app)

/deploy     (systemd unit, nginx site, backup script, server install guide)

/docs       (architecture, roadmap)



\---



\## 14. Primary Use Cases



\### Use Case 1 – Project Estimation



User uploads SRS → system generates modules, sprints, and cost estimate.



\### Use Case 2 – Tender Participation



User uploads tender → system evaluates eligibility → generates proposal documents.



\---



\## 15. Key Design Principles



\* Offline-first

\* Data privacy by design

\* Explainable AI outputs

\* Traceable cost calculations



\---



End of Manifest



