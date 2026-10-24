import logging

logger = logging.getLogger("zynex.eligibility")


def log_pipeline_step(step: str, chunk_id: str = None, page_no: int = None,
                      criterion_id: str = None, status: str = None, message: str = ""):
    details = []
    if chunk_id:
        details.append(f"chunk_id={chunk_id}")
    if page_no is not None:
        details.append(f"page_no={page_no}")
    if criterion_id:
        details.append(f"criterion_id={criterion_id}")
    if status:
        details.append(f"status={status}")
    detail_str = f" | {', '.join(details)}" if details else ""
    logger.info("[PIPELINE:%s] %s%s", step, message, detail_str)
