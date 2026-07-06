import asyncio
import time
from fastapi import FastAPI, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from loguru import logger
import redis.asyncio as redis
from sqlalchemy import select
from decimal import Decimal

from app.config import settings
from app.database import engine, get_db, async_session_maker
from app.dependencies import get_redis
from app.models import metadata
from app.users.models import User
from app.portfolio.models import Position
from app.auth.utils import hash_password
from app.market.service import initialize_prices_in_redis
from app.market.websocket import run_price_simulator_task

# 1. Setup SlowAPI rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["100 per minute"])

app = FastAPI(
    title=settings.APP_NAME,
    description="NobleVest Institutional Brokerage Platform Backend API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 2. Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Add Custom Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response

# 4. Logger Config
logger.remove()
logger.add(
    "logs/noblevest.log",
    rotation="10 MB",
    retention="10 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)
# Also output to stdout
import sys
logger.add(sys.stdout, colorize=True, format="<green>{time:HH:mm:ss}</green> <level>{message}</level>", level="INFO")

# 5. Seeding logic & background simulator startup during app startup
@app.on_event("startup")
async def startup_event():
    logger.info("Initializing database schemas...")
    # NOTE: In Docker compose env we run Alembic upgrade, but we also create_all as a safe fallback.
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)

    # Initialize prices in Redis
    redis_client = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    await initialize_prices_in_redis(redis_client)
    
    # Run Price Simulator background thread
    asyncio.create_task(run_price_simulator_task(redis_client))
    
    # Seed default Admin and initial portfolio dummy records if they don't exist
    async with async_session_maker() as session:
        # Check first admin
        admin_res = await session.execute(select(User).where(User.email == settings.FIRST_ADMIN_EMAIL))
        admin = admin_res.scalar_one_or_none()
        if not admin:
            hashed_pwd = hash_password(settings.FIRST_ADMIN_PASSWORD)
            admin = User(
                email=settings.FIRST_ADMIN_EMAIL,
                first_name="NobleVest",
                last_name="Administrator",
                password_hash=hashed_pwd,
                client_type="broker_dealer",
                role="admin",
                is_verified=True,
                is_active=True,
                kyc_status="approved"
            )
            session.add(admin)
            await session.commit()
            await session.refresh(admin)
            logger.info(f"Seeded first admin account: {settings.FIRST_ADMIN_EMAIL}")
            
            # Seed initial positions for this user to make the demo dashboard look awesome
            positions = [
                Position(user_id=admin.id, symbol="AAPL", name="Apple Inc.", asset_class="equity", quantity=Decimal("150.0"), avg_cost=Decimal("180.25"), currency="USD", exchange="NASDAQ"),
                Position(user_id=admin.id, symbol="NVDA", name="NVIDIA Corporation", asset_class="equity", quantity=Decimal("80.0"), avg_cost=Decimal("795.50"), currency="USD", exchange="NASDAQ"),
                Position(user_id=admin.id, symbol="BTC", name="Bitcoin USD", asset_class="crypto", quantity=Decimal("1.25"), avg_cost=Decimal("62000.00"), currency="USD", exchange="Coinbase")
            ]
            session.add_all(positions)
            await session.commit()
            logger.info(f"Seeded default portfolio positions for user {admin.email}")
            
    await redis_client.close()

# 6. Include routers
from app.auth.router import router as auth_router
from app.users.router import router as users_router
from app.portfolio.router import router as portfolio_router
from app.market.router import router as market_router
from app.market.websocket import router as ws_router
from app.contact.router import router as contact_router
from app.admin.router import router as admin_router

app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(portfolio_router, prefix="/api/v1")
app.include_router(market_router, prefix="/api/v1")
app.include_router(ws_router, prefix="/api/v1")
app.include_router(contact_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": settings.APP_NAME}
