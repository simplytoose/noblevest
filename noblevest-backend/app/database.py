import sys
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from app.config import settings

# In order to allow running alembic migrations or tests locally (where db is localhost, not db container)
# we can dynamically replace db:5432 with localhost:5432 if we are not running inside Docker
database_url = settings.DATABASE_URL
if "db:5432" in database_url and not os.path.exists("/.dockerenv"):
    database_url = database_url.replace("db:5432", "localhost:5432")

# Also import os for checking docker env
import os

engine = create_async_engine(
    database_url,
    echo=settings.DEBUG,
    future=True,
    pool_size=20,
    max_overflow=10
)

async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()

async def get_db():
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
