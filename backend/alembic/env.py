from alembic import context
from sqlalchemy import engine_from_config, pool

from app import models  # noqa: F401 - registers tables on Base.metadata
from app.config import get_settings
from app.db import Base, use_schema

config = context.config
# "%" (URL-encoded passwords) must be escaped for configparser interpolation.
config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    schema = get_settings().database_schema
    if schema and connectable.dialect.name == "postgresql":
        with connectable.begin() as conn:  # a fresh cloud database has no schema yet
            conn.exec_driver_sql('CREATE SCHEMA IF NOT EXISTS "' + schema.replace('"', '""') + '"')
        use_schema(connectable, schema)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
