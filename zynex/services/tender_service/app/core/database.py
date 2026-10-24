from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Register all models so FK relationships resolve in any context (including background tasks)
import app.models.user  # noqa: F401, E402
import app.models.document  # noqa: F401, E402
import app.models.project_documents  # noqa: F401, E402
import app.models.estimation  # noqa: F401, E402
import app.models.tender  # noqa: F401, E402
import app.models.knowledge_base  # noqa: F401, E402
import app.models.estimation_project  # noqa: F401, E402
