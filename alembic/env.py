"""Alembic environment configuration for JobPilot AI.

This module configures Alembic to work with SQLModel and the application's
database schema. It sets up dynamic database URL configuration, naming
conventions, and batch mode for SQLite compatibility.

Legacy ``ai-job-scraper`` tables (``jobsql``, ``companysql``,
``savedsearchsql``) are preserved in migrated databases but excluded from
autogenerate so ``alembic check`` compares only the JobPilot schema.
"""

from logging.config import fileConfig

from alembic import context
from jobpilot.config import Settings
from jobpilot.database.models import AppSQLModel
from sqlalchemy import engine_from_config, pool

_RETIRED_TABLES = {
    "jobsql",
    "companysql",
    "savedsearchsql",
    "_alembic_8f4b2c91a3d7_state",
    "_alembic_c91e7a4d2b6f_legacy_cost_imports",
}

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Set database URL from Settings
settings = Settings()
config.set_main_option("sqlalchemy.url", settings.db_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target_metadata to the application-owned registry for autogenerate support.
target_metadata = AppSQLModel.metadata

# Naming convention for cleaner constraint names
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def _include_object(object_, name, type_, reflected, compare_to) -> bool:
    """Exclude retired migration bookkeeping and legacy tables."""
    del object_, reflected, compare_to
    return not (type_ == "table" and name in _RETIRED_TABLES)


# Common configuration shared by online and offline modes
COMMON_CFG = {
    "target_metadata": target_metadata,
    "compare_type": True,
    "render_as_batch": True,  # Enable batch mode for SQLite
    "naming_convention": NAMING_CONVENTION,
    "include_object": _include_object,
}


def _configure_offline() -> None:
    """Configure context for offline migrations."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **COMMON_CFG,
    )


def _configure_online(connection) -> None:
    """Configure context for online migrations."""
    options = dict(COMMON_CFG)
    if connection.dialect.name == "sqlite":
        connection.connection.driver_connection.autocommit = False
        options["transactional_ddl"] = True
    context.configure(connection=connection, **options)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    _configure_offline()
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = config.attributes.get("connection", None)

    if connectable is None:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    if hasattr(connectable, "connect"):
        with connectable.connect() as connection:
            _configure_online(connection)
            with context.begin_transaction():
                context.run_migrations()
    else:
        _configure_online(connectable)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
