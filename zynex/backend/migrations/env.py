import sys
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Add backend to path so models can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.models.base import Base
import app.models  # noqa: F401  (registers every model)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Credentials come from the environment (DATABASE_URL), never from alembic.ini.
# The app uses asyncpg; Alembic runs synchronously, so swap in the psycopg2 driver.
from app.core.config import settings
config.set_main_option(
    "sqlalchemy.url",
    # '%' must be doubled: ConfigParser would read a percent-encoded password (e.g. %24) as interpolation syntax
    settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2").replace("%", "%%"),
)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url, target_metadata=target_metadata, literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
