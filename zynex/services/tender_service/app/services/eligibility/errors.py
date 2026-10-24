from typing import Optional


class EligibilityError(Exception):
    """Base exception for the tender eligibility pipeline."""

    def __init__(self, message: str, error_code: str = "INTERNAL_ERROR", run_id: Optional[str] = None):
        self.message = message
        self.error_code = error_code
        self.run_id = run_id
        super().__init__(message)


class FileValidationError(EligibilityError):
    def __init__(self, message: str, run_id: Optional[str] = None):
        super().__init__(message, error_code="FILE_VALIDATION_ERROR", run_id=run_id)


class ExtractionError(EligibilityError):
    def __init__(self, message: str, run_id: Optional[str] = None):
        super().__init__(message, error_code="EXTRACTION_ERROR", run_id=run_id)


class PipelineError(EligibilityError):
    def __init__(self, message: str, run_id: Optional[str] = None):
        super().__init__(message, error_code="PIPELINE_ERROR", run_id=run_id)
