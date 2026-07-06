import os
from celery import Celery
from celery.schedules import crontab
from loguru import logger
import asyncio
from datetime import date, timedelta
from decimal import Decimal

# Read environment variables
redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "noblevest",
    broker=redis_url,
    backend=redis_url
)

# Queue declarations
celery_app.conf.task_default_queue = "default"
celery_app.conf.task_routes = {
    "app.celery_app.take_daily_performance_snapshots": {"queue": "snapshots"}
}

# Beat scheduling
celery_app.conf.beat_schedule = {
    "daily-portfolio-snapshots": {
        "task": "app.celery_app.take_daily_performance_snapshots",
        "schedule": crontab(hour=23, minute=59), # 23:59 UTC daily
    }
}
celery_app.conf.timezone = "UTC"

# Celery task
@celery_app.task(name="app.celery_app.take_daily_performance_snapshots")
def take_daily_performance_snapshots():
    logger.info("Executing Celery Task: take_daily_performance_snapshots")
    
    # We must bridge synchronous Celery with asynchronous SQLAlchemy session
    # Run the async core inside an event loop
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    loop.run_until_complete(async_snapshot_executor())

async def async_snapshot_executor():
    from app.database import async_session_maker
    from app.users.models import User
    from app.portfolio.models import PerformanceSnapshot, Position
    from app.portfolio.service import calculate_portfolio_overview
    from app.dependencies import settings
    import redis.asyncio as redis
    from sqlalchemy import select
    
    # Initialize async Redis client
    redis_client = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    
    today = date.today()
    yesterday = today - timedelta(days=1)
    
    async with async_session_maker() as session:
        # Retrieve all active users
        res = await session.execute(select(User).where(User.is_active == True))
        users = res.scalars().all()
        
        for user in users:
            try:
                # Calculate current portfolio value
                overview = await calculate_portfolio_overview(session, redis_client, str(user.id))
                today_val = overview["total_value"]
                
                # Fetch yesterday's snapshot to compute daily return
                yest_res = await session.execute(
                    select(PerformanceSnapshot)
                    .where(PerformanceSnapshot.user_id == user.id, PerformanceSnapshot.date == yesterday)
                )
                yest_snapshot = yest_res.scalar_one_or_none()
                
                if yest_snapshot and yest_snapshot.portfolio_value > 0:
                    yest_val = yest_snapshot.portfolio_value
                    daily_ret = ((today_val - yest_val) / yest_val) * Decimal("100")
                else:
                    daily_ret = Decimal("0")
                
                # Calculate cumulative return since inception baseline
                inception_res = await session.execute(
                    select(PerformanceSnapshot)
                    .where(PerformanceSnapshot.user_id == user.id)
                    .order_by(PerformanceSnapshot.date.asc())
                    .limit(1)
                )
                inception_snapshot = inception_res.scalar_one_or_none()
                if inception_snapshot and inception_snapshot.portfolio_value > 0:
                    cum_ret = ((today_val - inception_snapshot.portfolio_value) / inception_snapshot.portfolio_value) * Decimal("100")
                else:
                    cum_ret = Decimal("0")
                
                # Insert or Update current snapshot
                snap_res = await session.execute(
                    select(PerformanceSnapshot)
                    .where(PerformanceSnapshot.user_id == user.id, PerformanceSnapshot.date == today)
                )
                current_snap = snap_res.scalar_one_or_none()
                
                if current_snap:
                    current_snap.portfolio_value = today_val
                    current_snap.daily_return = daily_ret
                    current_snap.cumulative_return = cum_ret
                else:
                    new_snap = PerformanceSnapshot(
                        user_id=user.id,
                        date=today,
                        portfolio_value=today_val,
                        daily_return=daily_ret,
                        cumulative_return=cum_ret
                    )
                    session.add(new_snap)
                    
                logger.info(f"Performance snapshot saved for user {user.email}: Value={today_val}")
                
            except Exception as ex:
                logger.error(f"Failed to record snapshot for user {user.email}: {ex}")
                
        await session.commit()
    await redis_client.close()
