from fastapi import APIRouter, Depends
from app.api.v1 import kb_files
from app.api.v1 import auth, documents, estimation, eligibility, knowledge_base, kb_company, proposals, project_documents, estimation_projects, ai_chat, tender, tender_tiger, app_settings
from app.core.security import require_access

router = APIRouter(prefix="/api/v1")

ALL_ROLES = ("admin", "analyst", "viewer")
WORK_ROLES = ("admin", "analyst")

# viewers: read-only; analysts/admins: read + write
_work = [Depends(require_access(read=ALL_ROLES, write=WORK_ROLES))]
# knowledge base: everyone reads, only admins write
_kb = [Depends(require_access(read=ALL_ROLES, write=("admin",)))]

router.include_router(auth.router)  # public: login
router.include_router(documents.router, dependencies=_work)
router.include_router(estimation.router, dependencies=_work)
router.include_router(eligibility.router)  # per-route require_role
router.include_router(tender.router, dependencies=_work)
router.include_router(tender_tiger.router, dependencies=_work)
router.include_router(app_settings.router)  # admin-only except /effective; per-route require_role
router.include_router(knowledge_base.router, dependencies=_kb)
router.include_router(kb_company.router, dependencies=_kb)
router.include_router(kb_files.router, dependencies=_kb)
router.include_router(proposals.router, dependencies=_work)
router.include_router(project_documents.router, dependencies=_kb)
router.include_router(estimation_projects.router, dependencies=_work)
router.include_router(ai_chat.router, dependencies=_work)
