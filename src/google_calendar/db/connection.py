"""Database connection management for Google Calendar MCP using PostgreSQL."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Optional

try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False
    asyncpg = None


# Global connection pool
_pool: Optional["asyncpg.Pool"] = None


def get_db_url() -> str:
    """
    Get database URL.

    Priority:
    1. DATABASE_URL environment variable (full connection string)
    2. Individual POSTGRES_* environment variables
    3. Default local development settings
    """
    # Full URL takes priority
    if url := os.environ.get("DATABASE_URL"):
        return url

    # Build from components
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ.get("POSTGRES_USER", "travel")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    database = os.environ.get("POSTGRES_DB", "google_calendar_mcp")

    if password:
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    return f"postgresql://{user}@{host}:{port}/{database}"


def get_schema_path() -> Path:
    """Get path to schema.sql file."""
    return Path(__file__).parent / "schema.sql"


def is_postgres_configured() -> bool:
    """Check if PostgreSQL is configured."""
    return bool(
        os.environ.get("DATABASE_URL") or
        os.environ.get("POSTGRES_HOST")
    )


async def create_pool(
    min_size: int = 2,
    max_size: int = 10,
    **kwargs
) -> "asyncpg.Pool":
    """Create connection pool.

    Args:
        min_size: Minimum pool size
        max_size: Maximum pool size
        **kwargs: Additional arguments for asyncpg.create_pool

    Returns:
        asyncpg.Pool instance
    """
    global _pool

    if not ASYNCPG_AVAILABLE:
        raise RuntimeError("asyncpg is not installed. Install with: pip install asyncpg")

    if _pool is not None:
        return _pool

    db_url = get_db_url()

    _pool = await asyncpg.create_pool(
        db_url,
        min_size=min_size,
        max_size=max_size,
        **kwargs
    )

    return _pool


async def get_pool() -> "asyncpg.Pool":
    """Get or create connection pool.

    Returns:
        asyncpg.Pool instance
    """
    global _pool

    if _pool is None:
        _pool = await create_pool()

    return _pool


async def close_pool() -> None:
    """Close connection pool."""
    global _pool

    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_db() -> AsyncGenerator["asyncpg.Connection", None]:
    """Get database connection as async context manager.

    Usage:
        async with get_db() as conn:
            rows = await conn.fetch("SELECT * FROM projects")

    Yields:
        asyncpg.Connection from pool
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        yield conn


async def init_db() -> None:
    """Initialize database with schema.

    Creates tables if they don't exist.
    """
    schema_path = get_schema_path()

    if not schema_path.exists():
        return

    schema_sql = schema_path.read_text()

    async with get_db() as conn:
        await conn.execute(schema_sql)


async def check_db_exists() -> bool:
    """Check if database tables exist.

    Returns:
        True if database is initialized
    """
    try:
        async with get_db() as conn:
            row = await conn.fetchrow("""
                SELECT EXISTS (
                    SELECT FROM pg_tables
                    WHERE schemaname = 'public'
                    AND tablename = 'projects'
                )
            """)
            return row[0] if row else False
    except Exception:
        return False


async def run_migrations(conn: "asyncpg.Connection") -> None:
    """Run schema migrations for existing databases."""
    # Get existing columns in projects table
    projects_cols = await conn.fetch("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'projects'
    """)
    projects_col_names = {row["column_name"] for row in projects_cols}

    # Projects migrations - add is_active if not exists
    if "is_active" not in projects_col_names:
        await conn.execute("""
            ALTER TABLE projects
            ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE
        """)


async def ensure_db_initialized() -> None:
    """Ensure database is initialized, create if needed.

    Call this at server startup.
    """
    try:
        if not await check_db_exists():
            await init_db()
        else:
            # Still run schema to ensure any new tables/views exist
            schema_path = get_schema_path()

            if schema_path.exists():
                schema_sql = schema_path.read_text()
                async with get_db() as conn:
                    await conn.execute(schema_sql)
                    # Run migrations for existing tables
                    await run_migrations(conn)
    except Exception as e:
        # Log error but don't fail - pool might not be ready yet
        print(f"Warning: Could not initialize database: {e}")


class DatabaseManager:
    """Database manager for lifespan management.

    Usage with FastMCP:
        db_manager = DatabaseManager()

        @asynccontextmanager
        async def lifespan(app):
            await db_manager.initialize()
            yield {"db_manager": db_manager}
            await db_manager.close()

        mcp = FastMCP("google-calendar", lifespan=lifespan)
    """

    def __init__(self, db_url: Optional[str] = None):
        """Initialize database manager.

        Args:
            db_url: Optional custom database URL
        """
        self._db_url = db_url
        self._initialized = False

    @property
    def db_url(self) -> str:
        """Get database URL."""
        return self._db_url or get_db_url()

    async def initialize(self) -> None:
        """Initialize database (create pool, schema)."""
        if self._initialized:
            return

        # Set environment variable if custom URL provided
        if self._db_url:
            os.environ["DATABASE_URL"] = self._db_url

        # Create pool
        await create_pool()

        # Initialize schema
        await ensure_db_initialized()

        self._initialized = True

    async def close(self) -> None:
        """Close connection pool."""
        await close_pool()
        self._initialized = False

    # Aliases for lifespan compatibility
    async def startup(self) -> None:
        """Alias for initialize()."""
        await self.initialize()

    async def shutdown(self) -> None:
        """Alias for close()."""
        await self.close()

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator["asyncpg.Connection", None]:
        """Get database connection.

        Yields:
            asyncpg.Connection
        """
        async with get_db() as conn:
            yield conn
