"""
Canonical field ontology — ~45 fields covering the full breadth of Indian
government procurement tenders.

Each entry is a FieldDef with:
  field_id        : canonical snake_case identifier (the enum value)
  value_type      : "numeric" | "boolean" | "string" | "date" | "array" |
                    "cert_object" | "bom_object" | "datetime"
  default_unit    : primary unit string (INR, Years, Days, Count, Hours …)
  comparison_semantics : description of how the rule engine evaluates this field
  profile_path    : dotted path into CompanyProfileV2 for this field
  group           : logical grouping for UI / prompt ordering
  criterion_types : which CriterionTypes this field typically appears in

Design note — anything that cannot map goes to "other", but the target is
≤15% REVIEW_REQUIRED, down from V1's 77%.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FieldDef:
    field_id:             str
    value_type:           str
    default_unit:         Optional[str]
    comparison_semantics: str
    profile_path:         str
    group:                str
    criterion_types:      List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Financial
# ---------------------------------------------------------------------------
FIELD_ANNUAL_TURNOVER = FieldDef(
    field_id="annual_turnover",
    value_type="numeric_series",
    default_unit="INR",
    comparison_semantics=(
        "For THRESHOLD: compare single value against latest or specified FY. "
        "For DISJUNCTIVE with quantifier: evaluate N-of-M condition over fy_list; "
        "requires per-FY series in profile — aggregate triggers MISSING."
    ),
    profile_path="financials.annual_turnover_by_fy",
    group="Financial",
    criterion_types=["THRESHOLD", "DISJUNCTIVE"],
)
FIELD_NET_WORTH = FieldDef(
    field_id="net_worth",
    value_type="numeric_series",
    default_unit="INR",
    comparison_semantics=">=  against latest FY net_worth; must be positive.",
    profile_path="financials.net_worth_by_fy",
    group="Financial",
    criterion_types=["THRESHOLD"],
)
FIELD_WORKING_CAPITAL = FieldDef(
    field_id="working_capital",
    value_type="numeric",
    default_unit="INR",
    comparison_semantics=">= threshold.",
    profile_path="financials.working_capital",
    group="Financial",
    criterion_types=["THRESHOLD"],
)
FIELD_SOLVENCY = FieldDef(
    field_id="solvency_certificate_val",
    value_type="numeric",
    default_unit="INR",
    comparison_semantics=">= solvency value from certificate.",
    profile_path="financials.solvency_amount",
    group="Financial",
    criterion_types=["THRESHOLD"],
)
FIELD_PAT = FieldDef(
    field_id="profit_after_tax",
    value_type="numeric_series",
    default_unit="INR",
    comparison_semantics="> 0 (profitability check); may be DISJUNCTIVE over FY.",
    profile_path="financials.pat_by_fy",
    group="Financial",
    criterion_types=["THRESHOLD", "DISJUNCTIVE"],
)
FIELD_EMD = FieldDef(
    field_id="emd_amount",
    value_type="numeric",
    default_unit="INR",
    comparison_semantics="== required EMD amount; payment mode checked as sub-condition.",
    profile_path="bidding_capability.emd_budget",
    group="Financial",
    criterion_types=["PROCEDURAL"],
)
FIELD_TENDER_FEE = FieldDef(
    field_id="tender_fee",
    value_type="numeric",
    default_unit="INR",
    comparison_semantics="== tender document fee.",
    profile_path="bidding_capability.fee_budget",
    group="Financial",
    criterion_types=["PROCEDURAL"],
)
FIELD_BID_VALIDITY = FieldDef(
    field_id="bid_validity_days",
    value_type="integer",
    default_unit="Days",
    comparison_semantics=">= required calendar days from submission date.",
    profile_path="bidding_capability.max_validity_days",
    group="Financial",
    criterion_types=["PROCEDURAL"],
)

# ---------------------------------------------------------------------------
# Legal / Registration
# ---------------------------------------------------------------------------
FIELD_INCORPORATION_TYPE = FieldDef(
    field_id="incorporation_type",
    value_type="string",
    default_unit=None,
    comparison_semantics="== or IN allowed_set (e.g. Pvt Ltd, LLP, Partnership).",
    profile_path="legal.incorporation_type",
    group="Legal",
    criterion_types=["THRESHOLD"],
)
FIELD_GST = FieldDef(
    field_id="gst_registration",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True; state match checked as sub-condition.",
    profile_path="legal.gstin_list",
    group="Legal",
    criterion_types=["DOCUMENT_REQUIRED", "THRESHOLD"],
)
FIELD_PAN = FieldDef(
    field_id="pan_card",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True (PAN must be held).",
    profile_path="legal.pan",
    group="Legal",
    criterion_types=["DOCUMENT_REQUIRED"],
)
FIELD_EPF = FieldDef(
    field_id="epf_registration",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True.",
    profile_path="legal.epf_code",
    group="Legal",
    criterion_types=["DOCUMENT_REQUIRED"],
)
FIELD_ESI = FieldDef(
    field_id="esi_registration",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True.",
    profile_path="legal.esi_code",
    group="Legal",
    criterion_types=["DOCUMENT_REQUIRED"],
)
FIELD_MSME_CATEGORY = FieldDef(
    field_id="msme_category",
    value_type="enum",
    default_unit=None,
    comparison_semantics=(
        "Graded enum: MICRO < SMALL < MEDIUM < LARGE. "
        "EMD exemption clauses specify Micro/Small — MEDIUM does NOT qualify. "
        "Never evaluate as a boolean; must compare against the graded enum."
    ),
    profile_path="legal.msme_category",
    group="Legal",
    criterion_types=["PROCEDURAL"],
)
FIELD_MSME_UDYAM = FieldDef(
    field_id="msme_udyam",
    value_type="string",
    default_unit=None,
    comparison_semantics="== True (Udyam registration held & number provided).",
    profile_path="legal.udyam_number",
    group="Legal",
    criterion_types=["DOCUMENT_REQUIRED"],
)

# Document Checklist / Submission Requirements
FIELD_COVER_LETTER = FieldDef(
    field_id="cover_letter",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True (Form 1 / Cover Letter submission).",
    profile_path="documents.cover_letter",
    group="Document Checklist",
    criterion_types=["DOCUMENT_REQUIRED"],
)
FIELD_BIDDER_PARTICULARS = FieldDef(
    field_id="bidder_particulars",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True (Bidder Company Details Form).",
    profile_path="documents.bidder_particulars",
    group="Document Checklist",
    criterion_types=["DOCUMENT_REQUIRED"],
)
FIELD_CA_TURNOVER_CERT = FieldDef(
    field_id="ca_turnover_certificate",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True (CA certified turnover statement).",
    profile_path="documents.ca_turnover_cert",
    group="Document Checklist",
    criterion_types=["DOCUMENT_REQUIRED"],
)
FIELD_NON_BLACKLISTING_DECL = FieldDef(
    field_id="non_blacklisting_declaration",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True (Notarized Affidavit / Undertaking).",
    profile_path="documents.non_blacklisting_decl",
    group="Document Checklist",
    criterion_types=["DOCUMENT_REQUIRED"],
)
FIELD_LETTER_OF_AUTH = FieldDef(
    field_id="letter_of_authorization",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True (Power of Attorney / Board Resolution).",
    profile_path="documents.letter_of_auth",
    group="Document Checklist",
    criterion_types=["DOCUMENT_REQUIRED"],
)
FIELD_CERT_INCORPORATION = FieldDef(
    field_id="certificate_of_incorporation",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True (COI / MoA / PoA copy).",
    profile_path="documents.coi",
    group="Document Checklist",
    criterion_types=["DOCUMENT_REQUIRED"],
)
FIELD_AUDITED_BALANCE_SHEET = FieldDef(
    field_id="audited_balance_sheet",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True (Audited financial statements for required FYs).",
    profile_path="documents.audited_balance_sheets",
    group="Document Checklist",
    criterion_types=["DOCUMENT_REQUIRED"],
)
FIELD_INCOME_TAX_RETURNS = FieldDef(
    field_id="income_tax_returns",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True (ITR acknowledgment for required FYs).",
    profile_path="documents.itr",
    group="Document Checklist",
    criterion_types=["DOCUMENT_REQUIRED"],
)
FIELD_WORK_ORDER_COPY = FieldDef(
    field_id="work_order_copy",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True (Signed Work Orders / Agreement Copies).",
    profile_path="documents.work_orders",
    group="Document Checklist",
    criterion_types=["DOCUMENT_REQUIRED"],
)
FIELD_PERFORMANCE_CERT = FieldDef(
    field_id="performance_certificate",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True (Client satisfaction / completion certificates).",
    profile_path="documents.performance_certs",
    group="Document Checklist",
    criterion_types=["DOCUMENT_REQUIRED"],
)
FIELD_TN_OFFICE_PROOF = FieldDef(
    field_id="tn_office_proof",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True (Proof of operational office in Tamil Nadu).",
    profile_path="documents.tn_office_proof",
    group="Document Checklist",
    criterion_types=["DOCUMENT_REQUIRED"],
)
FIELD_MANPOWER_RESUME = FieldDef(
    field_id="manpower_resume_required",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True (Key personnel CVs / deployment matrix).",
    profile_path="documents.key_personnel_cvs",
    group="Document Checklist",
    criterion_types=["DOCUMENT_REQUIRED"],
)

FIELD_STATE_OFFICE = FieldDef(
    field_id="state_office",
    value_type="array",
    default_unit=None,
    comparison_semantics="CONTAINS required state (e.g. Tamil Nadu).",
    profile_path="locations.office_states",
    group="Legal",
    criterion_types=["THRESHOLD"],
)
FIELD_BLACKLISTED = FieldDef(
    field_id="blacklisted",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== False (bidder must NOT be blacklisted).",
    profile_path="legal.blacklisted",
    group="Legal",
    criterion_types=["THRESHOLD"],
)

FIELD_INSOLVENCY = FieldDef(
    field_id="insolvency_status",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== False (bidder must NOT be insolvent, bankrupt or under liquidation).",
    profile_path="legal.insolvent",
    group="Legal",
    criterion_types=["THRESHOLD"],
)
FIELD_WEBSITE = FieldDef(
    field_id="company_website",
    value_type="string",
    default_unit=None,
    comparison_semantics="Bidder must have its own website (the URL is evidence).",
    profile_path="company.website",
    group="Legal",
    criterion_types=["THRESHOLD"],
)

# ---------------------------------------------------------------------------
# Experience
# ---------------------------------------------------------------------------
FIELD_SIMILAR_WORK = FieldDef(
    field_id="similar_work_value",
    value_type="numeric",
    default_unit="INR",
    comparison_semantics=(
        "For CONDITIONAL_PAIR: evaluate nested OR of (single >= X) OR "
        "(aggregate of 2 >= Y); each branch also checks software component value."
    ),
    profile_path="projects[].similar_value",
    group="Experience",
    criterion_types=["CONDITIONAL_PAIR", "THRESHOLD"],
)
FIELD_SOFTWARE_COMPONENT = FieldDef(
    field_id="software_component_value",
    value_type="numeric",
    default_unit="INR",
    comparison_semantics=">= software portion of a qualifying agreement.",
    profile_path="projects[].software_value",
    group="Experience",
    criterion_types=["CONDITIONAL_PAIR"],
)
FIELD_GOVT_PSU_EXP = FieldDef(
    field_id="govt_psu_experience",
    value_type="integer",
    default_unit="Projects",
    comparison_semantics=">= count of Govt/PSU/Statutory client projects.",
    profile_path="projects[client_type=GOVT]",
    group="Experience",
    criterion_types=["THRESHOLD"],
)
FIELD_CLOUD_OPS = FieldDef(
    field_id="cloud_ops_experience",
    value_type="integer",
    default_unit="Years",
    comparison_semantics=">= years operating cloud environments.",
    profile_path="experience.cloud_ops_years",
    group="Experience",
    criterion_types=["THRESHOLD"],
)
FIELD_CONTRACT_COUNT = FieldDef(
    field_id="contract_count",
    value_type="integer",
    default_unit="Count",
    comparison_semantics=">= number of qualifying contracts completed.",
    profile_path="projects.length",
    group="Experience",
    criterion_types=["THRESHOLD"],
)
FIELD_COMPLETION_CERT = FieldDef(
    field_id="completion_certificate",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True for each qualifying project.",
    profile_path="projects[].has_completion_cert",
    group="Experience",
    criterion_types=["DOCUMENT_REQUIRED"],
)
FIELD_PERFORMANCE_CERT = FieldDef(
    field_id="performance_certificate",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True for each qualifying project.",
    profile_path="projects[].has_performance_cert",
    group="Experience",
    criterion_types=["DOCUMENT_REQUIRED"],
)
FIELD_YEARS_IN_BUSINESS = FieldDef(
    field_id="experience_years",
    value_type="integer",
    default_unit="Years",
    comparison_semantics=">= operating years since incorporation.",
    profile_path="company_info.years_active",
    group="Experience",
    criterion_types=["THRESHOLD"],
)

# ---------------------------------------------------------------------------
# Certifications
# ---------------------------------------------------------------------------
FIELD_ISO_9001 = FieldDef(
    field_id="iso_9001",
    value_type="cert_object",
    default_unit=None,
    comparison_semantics="VALID and expiry_date > tender submission date.",
    profile_path="certifications.iso_9001",
    group="Certifications",
    criterion_types=["THRESHOLD"],
)
FIELD_ISO_20000 = FieldDef(
    field_id="iso_20000",
    value_type="cert_object",
    default_unit=None,
    comparison_semantics="VALID and expiry_date > tender submission date.",
    profile_path="certifications.iso_20000",
    group="Certifications",
    criterion_types=["THRESHOLD"],
)
FIELD_ISO_27001 = FieldDef(
    field_id="iso_27001",
    value_type="cert_object",
    default_unit=None,
    comparison_semantics="VALID and expiry_date > tender submission date.",
    profile_path="certifications.iso_27001",
    group="Certifications",
    criterion_types=["THRESHOLD"],
)
FIELD_CMMI = FieldDef(
    field_id="cmmi_level",
    value_type="integer",
    default_unit="Level",
    comparison_semantics=">= required level (e.g. CMMI Level 3).",
    profile_path="certifications.cmmi_level",
    group="Certifications",
    criterion_types=["THRESHOLD"],
)
FIELD_CERT_VALIDITY = FieldDef(
    field_id="cert_validity",
    value_type="date",
    default_unit="YYYY-MM-DD",
    comparison_semantics="> tender submission date.",
    profile_path="certifications[].expiry_date",
    group="Certifications",
    criterion_types=["THRESHOLD"],
)
FIELD_CERTIFICATIONS_GENERIC = FieldDef(
    field_id="certifications",
    value_type="array",
    default_unit=None,
    comparison_semantics="CONTAINS required cert name (normalised); expiry checked.",
    profile_path="certifications",
    group="Certifications",
    criterion_types=["THRESHOLD"],
)

# ---------------------------------------------------------------------------
# Manpower
# ---------------------------------------------------------------------------
FIELD_ROLE_COUNT = FieldDef(
    field_id="team_role_count",
    value_type="integer",
    default_unit="Count",
    comparison_semantics=">= required headcount for a specific role.",
    profile_path="manpower.roles[].count",
    group="Manpower",
    criterion_types=["CAPABILITY"],
)
FIELD_ROLE_QUAL = FieldDef(
    field_id="role_qualification",
    value_type="string",
    default_unit=None,
    comparison_semantics="MATCHES required degree/qualification string.",
    profile_path="manpower.roles[].degree",
    group="Manpower",
    criterion_types=["CAPABILITY"],
)
FIELD_ROLE_EXP = FieldDef(
    field_id="role_experience_years",
    value_type="integer",
    default_unit="Years",
    comparison_semantics=">= min experience years for that role.",
    profile_path="manpower.roles[].avg_experience",
    group="Manpower",
    criterion_types=["CAPABILITY"],
)
FIELD_ONSITE = FieldDef(
    field_id="onsite_availability",
    value_type="integer",
    default_unit="Days",
    comparison_semantics=">= days per month on-site.",
    profile_path="manpower.onsite_capacity",
    group="Manpower",
    criterion_types=["CAPABILITY"],
)
FIELD_LANGUAGE = FieldDef(
    field_id="language_proficiency",
    value_type="array",
    default_unit=None,
    comparison_semantics="CONTAINS required language (e.g. Tamil, English).",
    profile_path="manpower.languages",
    group="Manpower",
    criterion_types=["CAPABILITY"],
)

# ---------------------------------------------------------------------------
# Technical / BOM
# ---------------------------------------------------------------------------
FIELD_COMPUTE = FieldDef(
    field_id="compute_spec",
    value_type="bom_object",
    default_unit="vCPU/GB-RAM",
    comparison_semantics=">= required vCPU and RAM from BOM line item.",
    profile_path="infrastructure.compute_quota",
    group="Technical",
    criterion_types=["CAPABILITY"],
)
FIELD_STORAGE = FieldDef(
    field_id="storage_spec",
    value_type="bom_object",
    default_unit="TB/IOPS",
    comparison_semantics=">= storage capacity and IOPS from BOM.",
    profile_path="infrastructure.storage_quota",
    group="Technical",
    criterion_types=["CAPABILITY"],
)
FIELD_HA = FieldDef(
    field_id="ha_requirement",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True (HA architecture supported).",
    profile_path="infrastructure.ha_supported",
    group="Technical",
    criterion_types=["CAPABILITY"],
)
FIELD_DR_RPO = FieldDef(
    field_id="dr_rpo",
    value_type="numeric",
    default_unit="Hours",
    comparison_semantics="<= required RPO in hours.",
    profile_path="infrastructure.dr_rpo_hours",
    group="Technical",
    criterion_types=["CAPABILITY"],
)
FIELD_DR_RTO = FieldDef(
    field_id="dr_rto",
    value_type="numeric",
    default_unit="Hours",
    comparison_semantics="<= required RTO in hours.",
    profile_path="infrastructure.dr_rto_hours",
    group="Technical",
    criterion_types=["CAPABILITY"],
)
FIELD_SECURITY = FieldDef(
    field_id="security_controls",
    value_type="array",
    default_unit=None,
    comparison_semantics="CONTAINS all required controls (WAF, DDoS, OWASP, SSL).",
    profile_path="infrastructure.security_features",
    group="Technical",
    criterion_types=["CAPABILITY"],
)
FIELD_BANDWIDTH = FieldDef(
    field_id="bandwidth_allowance",
    value_type="numeric",
    default_unit="TB",
    comparison_semantics=">= monthly transfer allowance.",
    profile_path="infrastructure.bandwidth_tb",
    group="Technical",
    criterion_types=["CAPABILITY"],
)
FIELD_OS_DB = FieldDef(
    field_id="os_db_requirement",
    value_type="array",
    default_unit=None,
    comparison_semantics="CONTAINS required OS and DB stack elements.",
    profile_path="infrastructure.supported_stack",
    group="Technical",
    criterion_types=["CAPABILITY"],
)
FIELD_CSP = FieldDef(
    field_id="csp_empanelment",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True (MeitY empanelled CSP).",
    profile_path="infrastructure.meity_empanelled",
    group="Technical",
    criterion_types=["CAPABILITY"],
)
FIELD_PROJECT_VALUE = FieldDef(
    field_id="project_value",
    value_type="numeric",
    default_unit="INR",
    comparison_semantics=">= single project or aggregate project value.",
    profile_path="projects[].total_value",
    group="Technical",
    criterion_types=["THRESHOLD"],
)
FIELD_NET_WORTH_GENERIC = FieldDef(
    field_id="net_worth",
    value_type="numeric_series",
    default_unit="INR",
    comparison_semantics=">= positive threshold in specified FY.",
    profile_path="financials.net_worth_by_fy",
    group="Financial",
    criterion_types=["THRESHOLD"],
)

# ---------------------------------------------------------------------------
# Procedural
# ---------------------------------------------------------------------------
FIELD_SUBMISSION_DEADLINE = FieldDef(
    field_id="submission_deadline",
    value_type="datetime",
    default_unit="ISO8601",
    comparison_semantics="System time < deadline (tender still open).",
    profile_path="N/A (system clock)",
    group="Procedural",
    criterion_types=["PROCEDURAL"],
)
FIELD_DSC = FieldDef(
    field_id="dsc_required",
    value_type="enum",
    default_unit=None,
    comparison_semantics="== required DSC class (e.g. Class 3).",
    profile_path="bidding_capability.dsc_class",
    group="Procedural",
    criterion_types=["PROCEDURAL"],
)
FIELD_TWO_COVER = FieldDef(
    field_id="two_cover_submission",
    value_type="boolean",
    default_unit=None,
    comparison_semantics="== True (bidder supports two-cover upload).",
    profile_path="bidding_capability.supports_two_cover",
    group="Procedural",
    criterion_types=["PROCEDURAL"],
)

# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------
FIELD_OTHER = FieldDef(
    field_id="other",
    value_type="string",
    default_unit=None,
    comparison_semantics=(
        "Non-canonical — routes to REVIEW_REQUIRED. "
        "Target: ≤15% of all criteria. Any field that cannot be mapped to a "
        "canonical FieldDef must land here and be reviewed by the bid manager."
    ),
    profile_path="raw_profile",
    group="Fallback",
    criterion_types=["THRESHOLD", "CAPABILITY", "PROCEDURAL"],
)

# ---------------------------------------------------------------------------
# Master registry — ordered for prompt few-shot ordering (Financial first)
# ---------------------------------------------------------------------------
FIELD_REGISTRY: dict[str, FieldDef] = {
    f.field_id: f for f in [
        # Financial
        FIELD_ANNUAL_TURNOVER, FIELD_NET_WORTH, FIELD_WORKING_CAPITAL,
        FIELD_SOLVENCY, FIELD_PAT, FIELD_EMD, FIELD_TENDER_FEE,
        FIELD_BID_VALIDITY, FIELD_NET_WORTH_GENERIC,
        # Legal
        FIELD_INCORPORATION_TYPE, FIELD_GST, FIELD_PAN, FIELD_EPF, FIELD_ESI,
        FIELD_MSME_CATEGORY, FIELD_MSME_UDYAM, FIELD_STATE_OFFICE, FIELD_BLACKLISTED,
        FIELD_INSOLVENCY, FIELD_WEBSITE,
        # Experience
        FIELD_SIMILAR_WORK, FIELD_SOFTWARE_COMPONENT, FIELD_GOVT_PSU_EXP,
        FIELD_CLOUD_OPS, FIELD_CONTRACT_COUNT, FIELD_COMPLETION_CERT,
        FIELD_PERFORMANCE_CERT, FIELD_YEARS_IN_BUSINESS,
        # Certifications
        FIELD_ISO_9001, FIELD_ISO_20000, FIELD_ISO_27001, FIELD_CMMI,
        FIELD_CERT_VALIDITY, FIELD_CERTIFICATIONS_GENERIC,
        # Manpower
        FIELD_ROLE_COUNT, FIELD_ROLE_QUAL, FIELD_ROLE_EXP, FIELD_ONSITE, FIELD_LANGUAGE,
        # Technical / BOM
        FIELD_COMPUTE, FIELD_STORAGE, FIELD_HA, FIELD_DR_RPO, FIELD_DR_RTO,
        FIELD_SECURITY, FIELD_BANDWIDTH, FIELD_OS_DB, FIELD_CSP, FIELD_PROJECT_VALUE,
        # Procedural
        FIELD_SUBMISSION_DEADLINE, FIELD_DSC, FIELD_TWO_COVER,
        # Fallback
        FIELD_OTHER,
    ]
}

CANONICAL_FIELD_IDS: set[str] = set(FIELD_REGISTRY.keys())

# ---------------------------------------------------------------------------
# Helper used by LLMExtractor and PostValidator
# ---------------------------------------------------------------------------

FIELD_ALIASES: dict[str, str] = {
    "insolvency": "insolvency_status", "insolvent": "insolvency_status", "insolvency status": "insolvency_status",
    "bankruptcy": "insolvency_status", "liquidation": "insolvency_status", "solvency_status": "insolvency_status",
    "website": "company_website", "own_website": "company_website", "company website": "company_website",
    "bid_validity": "bid_validity_days",
    "bid validity": "bid_validity_days",
    "validity": "bid_validity_days",
    "validity_days": "bid_validity_days",
    "bid validity days": "bid_validity_days",
    "submission_deadline": "submission_deadline",
    "submission deadline": "submission_deadline",
    "submission_time": "submission_deadline",
    "submission time": "submission_deadline",
    "bid_submission": "submission_deadline",
    "bid submission": "submission_deadline",
    "deadline": "submission_deadline",
    "due_date": "submission_deadline",
    "due_time": "submission_deadline",
    "server time": "submission_deadline",
    "turnover": "annual_turnover",
    "annual turnover": "annual_turnover",
    "annual_turnover": "annual_turnover",
    "net_worth": "net_worth",
    "net worth": "net_worth",
    "solvency": "solvency_certificate_val",
    "solvency_certificate_val": "solvency_certificate_val",
    "experience": "experience_years",
    "experience_years": "experience_years",
    "experience years": "experience_years",
    "years_in_business": "experience_years",
    "project_value": "project_value",
    "project value": "project_value",
    "similar_work_value": "similar_work_value",
    "similar work value": "similar_work_value",
    "certifications": "certifications",
    "certification": "certifications",
    "certs": "certifications",
    "employee_count": "employee_count",
    "total_employees": "employee_count",
    "employees": "employee_count",
    "iso_9001": "iso_9001",
    "iso_27001": "iso_27001",
    "cmmi": "cmmi",
    "blacklisted": "blacklisted",
    "language": "language_proficiency",
    "language_proficiency": "language_proficiency",
    "language proficiency": "language_proficiency",
    "gst": "gst_registration",
    "gst_registration": "gst_registration",
    "pan": "pan_card",
    "pan_card": "pan_card",
    "emd": "emd_amount",
    "emd_amount": "emd_amount",
    "bid_security": "emd_amount",
    # Form and Document Checklist mappings
    "tender_document_complete": "tender_document_complete",
    "complete_bid_document": "tender_document_complete",
    "cover_letter": "cover_letter",
    "form 1": "cover_letter",
    "form_1": "cover_letter",
    "bidder_particulars": "bidder_particulars",
    "form 2": "bidder_particulars",
    "form_2": "bidder_particulars",
    "technical_checklist": "technical_checklist",
    "form 3": "technical_checklist",
    "form_3": "technical_checklist",
    "non_blacklisting_declaration": "non_blacklisting_declaration",
    "form 4": "non_blacklisting_declaration",
    "form_4": "non_blacklisting_declaration",
    "letter_of_authorization": "letter_of_authorization",
    "authorization_letter": "letter_of_authorization",
    "power_of_attorney": "letter_of_authorization",
    "certificate_of_incorporation": "certificate_of_incorporation",
    "incorporation_certificate": "certificate_of_incorporation",
    "audited_balance_sheet": "audited_balance_sheet",
    "balance_sheet": "audited_balance_sheet",
    "audited_pl_account": "audited_pl_account",
    "profit_and_loss": "audited_pl_account",
    "ca_turnover_certificate": "ca_turnover_certificate",
    "turnover_certificate": "ca_turnover_certificate",
    "income_tax_returns": "income_tax_returns",
    "itr": "income_tax_returns",
    "registration_certificate": "registration_certificate",
    "experience_certificates": "experience_certificates",
    "work_order_agreement_copy": "work_order_agreement_copy",
    "work_order": "work_order_agreement_copy",
    "performance_certificate": "performance_certificate",
    "technology_stack_certificate": "technology_stack_certificate",
    "cloud_work_order": "cloud_work_order",
    "experience_format_1": "experience_format_1",
    "experience_format_2": "experience_format_2",
    "tn_office_proof": "tn_office_proof",
    "tn_office_undertaking": "tn_office_undertaking",
    "software_dev_experience_evidence": "software_dev_experience_evidence",
    "cloud_ops_experience_evidence": "cloud_ops_experience_evidence",
    "single_agreement_evidence": "single_agreement_evidence",
    "two_agreement_evidence": "two_agreement_evidence",
    "turnover_proof_5fy": "turnover_proof_5fy",
    # Technical Stack & Security Frameworks
    "owasp": "security_controls",
    "owasp compliance": "security_controls",
    "owasp_compliance": "security_controls",
    "security_compliance": "security_controls",
    "backend_frameworks": "technology_stack_certificate",
    "backend frameworks": "technology_stack_certificate",
    "programming_languages": "technology_stack_certificate",
    "programming languages": "technology_stack_certificate",
    "api_protocols": "technology_stack_certificate",
    "api_architecture": "technology_stack_certificate",
    "restful_apis": "technology_stack_certificate",
    "graphql": "technology_stack_certificate",
    "grpc": "technology_stack_certificate",
    "mqtt": "technology_stack_certificate",
    # Manpower and Team
    "manpower_project_manager": "manpower_project_manager",
    "project_manager": "manpower_project_manager",
    "manpower_senior_fullstack": "manpower_senior_fullstack",
    "senior_fullstack": "manpower_senior_fullstack",
    "manpower_junior_fullstack": "manpower_junior_fullstack",
    "junior_fullstack": "manpower_junior_fullstack",
    "cvs_qualifications": "cvs_qualifications",
    "resumes": "cvs_qualifications",
    "technical_proposal": "technical_proposal",
    "cloud_bom_compliance": "cloud_bom_compliance",
    "sla_compliance": "sla_compliance",
    "msme_emd_exemption": "msme_emd_exemption",
    "boq_price_bid": "boq_price_bid",
    "dsc_required": "dsc_required",
    "digital_signature": "dsc_required",
    "technical_bid_part1": "technical_bid_part1",
    "price_bid_part2": "price_bid_part2",
    "documents_signed_stamped": "documents_signed_stamped",
    "documents_notarised": "documents_notarised",
    "no_alteration_certificate": "no_alteration_certificate",
    "originals_available": "originals_available",
    "prebid_addendum_compliance": "prebid_addendum_compliance",
    "proposal_index": "proposal_index",
    "final_upload_verification": "final_upload_verification"
}

def canonicalize_field(raw_field: str) -> str:
    """
    Return the canonical field_id for raw_field, or 'other' if no match.
    Tries alias lookup first, then exact match, then substring match, then keyword heuristics.
    """
    if not raw_field:
        return "other"
    normalized = raw_field.lower().strip()
    if normalized in FIELD_ALIASES:
        return FIELD_ALIASES[normalized]
    if normalized in CANONICAL_FIELD_IDS:
        return normalized
    token_form = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
    for alias, fid in FIELD_ALIASES.items():
        a = re.sub(r"[^a-z0-9]+", " ", alias.lower()).strip()
        if a and re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", token_form):
            return fid
    for fid in CANONICAL_FIELD_IDS:
        f = fid.replace("_", " ")
        if re.search(rf"(?<![a-z0-9]){re.escape(f)}(?![a-z0-9])", token_form):
            return fid

    # Smart Keyword Fallback Heuristics
    if "black" in normalized or "debar" in normalized:
        return "blacklisted"
    if "net worth" in normalized or "net_worth" in normalized:
        return "net_worth"
    if re.search(r"\bdsc\b", token_form) or "digital sign" in normalized or "signature" in normalized:
        return "dsc_required"
    if "boq" in normalized or "price bid" in normalized:
        return "boq_price_bid"
    if "senior full" in normalized or "senior_full" in normalized:
        return "manpower_senior_fullstack"
    if "junior full" in normalized or "junior_full" in normalized:
        return "manpower_junior_fullstack"
    if re.search(r"\b(?:cvs?|resumes?)\b", token_form):
        return "cvs_qualifications"
    if re.search(r"\bsla\b", token_form) or "service level" in normalized:
        return "sla_compliance"
    if re.search(r"\bindex\b", token_form):
        return "proposal_index"
    if re.search(r"\b(?:upload|verification)\b", token_form):
        return "final_upload_verification"
    if re.search(r"\boriginals?\b", token_form):
        return "originals_available"
    if "ca turnover" in normalized or "ca cert" in normalized or "chartered accountant" in normalized:
        return "ca_turnover_certificate"
    if "turnover proof" in normalized or "turnover evidence" in normalized or "5fy" in normalized:
        return "turnover_proof_5fy"
    if "tech stack" in normalized or "technology stack" in normalized:
        return "technology_stack_certificate"
    if "format 1" in normalized or "format-1" in normalized or "format_1" in normalized:
        return "experience_format_1"
    if "format 2" in normalized or "format-2" in normalized or "format_2" in normalized:
        return "experience_format_2"
    if "complete bid" in normalized or "tender document complete" in normalized:
        return "tender_document_complete"
    if "form 1" in normalized or "form-1" in normalized or "form_1" in normalized:
        return "cover_letter"
    if "form 2" in normalized or "form-2" in normalized or "form_2" in normalized:
        return "bidder_particulars"
    if "form 3" in normalized or "form-3" in normalized or "form_3" in normalized:
        return "technical_checklist"
    if "form 4" in normalized or "form-4" in normalized or "form_4" in normalized:
        return "non_blacklisting_declaration"

    return "other"
