from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class ChunkSchema(BaseModel):
    chunk_id: str
    run_id: Optional[str] = None
    physical_page: int
    printed_page: Optional[int] = None
    source_pages: Optional[List[int]] = None
    chapter: Optional[str] = None
    section: Optional[str] = None
    clause: Optional[str] = None
    content_type: str  # table|clause|section|page_text
    table_data: Optional[Dict[str, Any]] = None
    chunk_text: str
    char_count: int
    is_scanned: bool = False
    ocr_used: bool = False


class CriterionSchema(BaseModel):
    criterion_id: str = Field(..., description="Unique criterion ID, e.g. C001")
    chunk_id: Optional[str] = Field(None, description="Source chunk ID from which this criterion was extracted")
    page_no: int = Field(..., description="Physical page number")
    section: Optional[str] = Field(None, description="Section heading or clause")
    field: str = Field(..., description="Canonical field name")
    operator: str = Field(..., description="Comparison operator, e.g. >=, <=, ==, in, contains")
    value: Any = Field(..., description="Extracted raw criterion value")
    unit: Optional[str] = Field(None, description="Unit e.g. INR, Years, Date")
    mandatory: bool = Field(True, description="Whether criterion is mandatory")
    source_text: str = Field(..., description="Exact verbatim text snippet from document")
    exact_match: bool = Field(True, description="Grounding verification result: true if source_text exists in chunk text")
    alignment: Optional[Dict[str, Any]] = Field(None, description="S8: how the requirement maps onto the company knowledge base")
    alt_group: Optional[str] = Field(None, description="Criteria in one group are alternatives ('X or Y or Z'): meeting one is enough")
    group: Optional[str] = Field(None, description="Bidder category this requirement belongs to (e.g. 'Category 2 — Bihar-based firms'); None = every bidder")


class CriterionResultSchema(BaseModel):
    criterion_id: str
    page_no: int
    field: str
    status: str  # PASS | FAIL | MISSING | ERROR | NEEDS_REVIEW | INFORMATIONAL
    tender_value: Any
    company_value: Any
    mandatory: bool
    source_text: str
    ai_reasoning: Optional[str] = Field(None, description="Detailed AI reasoning and auditor explanation")
    operator: Optional[str] = None
    section: Optional[str] = None
    grounded: bool = True                      # source_text verified in the tender
    evidence: Optional[str] = None             # what the company record showed
    is_document: bool = False                  # a document the bidder must submit
    alignment: Optional[Dict[str, Any]] = None  # S8: the knowledge-base entity, normalised requirement, matched records
    alt_group: Optional[str] = None             # alternatives of one requirement ('X or Y or Z'): the best one counts
    group: Optional[str] = None                 # bidder category the requirement belongs to; None = every bidder
