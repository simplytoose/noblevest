import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from typing import AsyncGenerator

from app.database import Base
from app.config import settings
from app.main import app
from app.dependencies import get_db, get_redis

# Test database settings (in-memory sqlite is standard for tests, but we'll use a separate postgres url or postgres test container if needed)
# For simplicity, we can reuse the database engine with a suffix or run migrations. 
# Here, we set up a postgres test engine pointing to localhost or db depending on docker setup.
# In local test context, we'll swap settings database url to test db if needed.
# Since sqlite doesn't support UUID gen_random_uuid() out of the box, we use the same postgres instance or mock.
# We will define a scoped pytest-asyncio db setup.

# Replace DB url for testing if needed
TEST_DATABASE_URL = settings.DATABASE_URL.replace("noblevest", "noblevest_test") if "noblevest" in settings.DATABASE_URL else "postgresql+asyncpg://noblevest:strongpassword123@localhost:5432/noblevest_test"

@pytest.fixture(scope="session")
def event_loop():
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop

@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        # Create schema for testing
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    async_session = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    async with async_session() as session:
        yield session
        # Clean up database tables after each test
        await session.execute(Base.metadata.clear)

@pytest_asyncio.fixture
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    # Override database dependency
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(app=app, base_url="http://testserver") as ac:
        yield ac
        
    app.dependency_overrides.clear()
