from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# PostgreSQL in deployment (DATABASE_URL from the environment / GitLab CI variables).
# Local development and tests fall back to a SQLite file when DATABASE_URL is unset.
DEFAULT_SQLITE_URL = "sqlite+aiosqlite:///./island_dev.db"
DATABASE_URL = os.getenv("DATABASE_URL") or DEFAULT_SQLITE_URL

def json_type():
    """JSONB on PostgreSQL, plain JSON elsewhere (SQLite). A new instance per call: wrapping a
    shared instance in MutableList/MutableDict.as_mutable would affect every column using it."""
    return JSON().with_variant(JSONB(), "postgresql")


JSONType = json_type()   # plain (non-mutable) JSON columns may share this instance

# Base class for ORM models
Base = declarative_base()

engine = None
AsyncSessionLocal = None


def configure_database(url: str | None = None):
    """(Re)create the engine; tests call this with a temporary SQLite URL."""
    global engine, AsyncSessionLocal, DATABASE_URL
    DATABASE_URL = url or DATABASE_URL
    engine = create_async_engine(DATABASE_URL, echo=os.getenv("SQL_ECHO") == "1")
    AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    return engine


configure_database()


def get_db():
    session = AsyncSessionLocal()
    return session

# Function to create tables on startup
async def init_db():
    from . import models, game_models  # noqa: F401  (register tables)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


# Columns added after a table was first created (create_all never alters existing tables).
_ADDED_COLUMNS = {
    "ie_participants": {"condition": "VARCHAR(20)"},
}


def _add_missing_columns(sync_conn) -> None:
    from sqlalchemy import inspect, text

    insp = inspect(sync_conn)
    for table, cols in _ADDED_COLUMNS.items():
        if not insp.has_table(table):
            continue
        have = {c["name"] for c in insp.get_columns(table)}
        for name, ddl in cols.items():
            if name not in have:
                sync_conn.execute(text(f'ALTER TABLE {table} ADD COLUMN "{name}" {ddl}'))
