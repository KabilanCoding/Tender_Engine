from fastapi import APIRouter, Depends
from app.api.v1 import tender, tender_tiger, eligibility
from app.core.security import require_access

router = APIRouter(prefix="/api/v1")

ALL_ROLES = ("admin", "analyst", "viewer")
WORK_ROLES = ("admin", "analyst")

# viewers: read-only; analysts/admins: read + write
_work = [Depends(require_access(read=ALL_ROLES, write=WORK_ROLES))]

router.include_router(tender.router, dependencies=_work)
router.include_router(tender_tiger.router, dependencies=_work)
router.include_router(eligibility.router)

