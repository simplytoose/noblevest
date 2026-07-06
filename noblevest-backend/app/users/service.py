from sqlalchemy.ext.asyncio import AsyncSession
from app.users.models import ActivityLog
import json

async def log_activity(
    db: AsyncSession,
    user_id: str,
    action: str,
    ip_address: str = None,
    user_agent: str = None,
    metadata: dict = None
):
    activity = ActivityLog(
        user_id=user_id,
        action=action,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=metadata
    )
    db.add(activity)
    await db.commit()
