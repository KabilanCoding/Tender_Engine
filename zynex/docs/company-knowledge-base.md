# Company knowledge base: what is stored, how, and why

## Two kinds of company data, handled differently
| Kind | Examples | Where it lives | How the engine uses it |
|---|---|---|---|
| **Exact facts** | turnover, net worth, project value and dates, certificate validity, headcount, GSTIN / PAN / CIN, address | normal tables (`financial_records`, `projects`, `certifications`, `employees`, `company_profile` ...) | read by code and compared with numbers: never searched, never guessed |
| **Meaning** | "which projects count as railway / smart-city / e-governance work", "who is a project manager" | `kb_passage`: one short text per row + its embedding | finds *which rows* look relevant. The rule engine then checks their numbers. A match found only by meaning is shown as **check by hand**, never as a pass |

## Loaded from `Xenovex_Technology-KB.xlsx`
Sheets 01-07 (profile, financials, certificates, projects, employees, clients, technologies).

**Not loaded on purpose**
- Sheet 00 (cover) and sheet 08 (expected verdicts): sheet 08 is an answer key, not company data. Use it as a test list.
- The "derived metrics" rows of sheet 02 (averages, "PASS" text): the engine computes these itself.
- Not put in the search index: bank account, IFSC, e-mail addresses, GSTIN / PAN (`company_profile` is never indexed).

Money is stored in rupees (the workbook is in crore, multiplied by 1e7). A financial year is stored as the year it ends (FY 2023-24 -> 2024).

## How the search works
1. The query is the requirement's own sentence (no keyword list decides whether to search), only for requirements about kinds of work or kinds of people.
2. **Hybrid score** = 65% meaning (embedding similarity, bge-m3 by default; chosen on the Settings page) + 35% keywords (rare words and synonyms: "railway" also counts rail / metro / train / transit; the vocabulary covers railways, smart city, healthcare, tax, power, water, ports, banking, education, surveillance, tolls, public distribution and the software kinds).
3. **Keyword-only fallback**: if the embedding model cannot be reached the search still runs on keywords and demands a strong match.
4. **Optional AI re-check** (Settings: "Double-check meaning matches with the AI"): the model re-reads the best few matches, drops the ones that do not fit and gives a short reason. If it fails the matches stay as found.
5. The matched rows are only *candidates*. Values, dates, client type, experience years and qualifications are then read from the tables by code. A project or person found only by meaning is shown as "check by hand".

## Commands (from `backend/`)
```bash
python -m scripts.import_company_kb ../Xenovex_Technology-KB.xlsx                   # dry run: reads and checks, writes nothing
python -m scripts.import_company_kb ../Xenovex_Technology-KB.xlsx --apply           # upsert by ID; safe to re-run
python -m scripts.import_company_kb ../Xenovex_Technology-KB.xlsx --apply --replace-demo   # also remove the demo seed rows
```
The import ends by refreshing the search index. It can also be refreshed from the Knowledge Base page ("Refresh search index") or `POST /api/v1/kb/index/rebuild`.

## Things the workbook still needs (the importer warns about them)
- Financial years after FY 2023-24. Without them a tender asking for "the last 3 years" stays "check by hand".
- ISO 27001 validity differs between the profile sheet (2028-03-31) and the certificates sheet (2028-01-14). The certificates sheet is used.
- ISO 14001 expires 2026-10-31.
- Three project clients are not in the client directory sheet.

## Settings (Settings page, "Tender analysis")
- `Match experience by meaning` (on/off) and `Meaning match: minimum score` (default 0.62, higher = stricter).

## Company master screens (migration 0007)
The Knowledge Base page has nine tabs: identity and registration, financial performance, technical capabilities, certifications,
projects portfolio, workforce and roster, clients, partners and offices, legal and compliance.

| New | Where it is stored |
|---|---|
| Identity, registrations, MSME / start-up, banking limits, legal answers (blacklisted, debarred, insolvency, litigation), consortium and bidding capability | `company_profile` (one fact per row, grouped on screen by `app/api/v1/kb_company.py`). Bank account and IFSC are masked on screen and never indexed |
| Financial years (turnover, net worth, working capital, profit, EBITDA, auditor) | `financial_records` (existing table, now editable) |
| OEM partnerships | new table `oem_partnerships` |
| Offices | new table `company_offices` |
| Employee work mode, joining date, key-personnel flag, government and relevant experience | new `employees` columns |
| Work-order date, our role, evidence file names | new `projects` columns |

**Sample values.** `python -m scripts.seed_kb_sample --apply` fills only empty cells so every tab has something to show. Profile facts, offices and
OEM partners it adds are saved with `is_sample = true` (internal flag, not shown on screen). Editing and saving a value verifies it.
Employee and project columns are derived from the data already on the row (the engine does not read them).

**S9 (rule engine) changes.** A value that has not been verified yet (still the placeholder) never decides a pass or fail; it is reported as "check by hand" and tells the user to open, check and save it.
- `blacklisted` and `insolvency_status` criteria: PASS only from a recorded "no", FAIL from a recorded "yes", MISSING when nothing is recorded.
- `state_office`: uses the offices table as well as the registered address.
- Registration facts (GSTIN, PAN, website, EPF, ESI): a sample number is "check by hand", not a pass.
- Requirements that mention an OEM authorisation or a consortium / joint venture list what is on file, always as "check by hand".
