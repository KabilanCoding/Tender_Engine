"""Import every model so SQLAlchemy and Alembic see the whole schema from one place."""
from app.models.base import Base  # noqa: F401
from app.models import (  # noqa: F401
    app_setting,
    document,
    estimation,
    estimation_project,
    knowledge_base,
    project_documents,
    tender,
    user,
)
