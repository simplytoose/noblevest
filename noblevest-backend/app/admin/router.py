from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from typing import List, Optional
from uuid import UUID

from app.database import get_db
from app.dependencies import get_current_admin
from app.users.models import User
from app.users.schemas import UserResponse, UserUpdate
from app.contact.models import ContactRequest
from app.contact.schemas import ContactRequestResponse
from app.portfolio.models import Transaction, Position
from app.portfolio.schemas import TransactionResponse, PositionResponse
from app.portfolio.service import get_positions_with_metrics, calculate_portfolio_overview
import redis.asyncio as redis
from app.dependencies import get_redis

router = APIRouter(prefix="/admin", tags=["Admin Panel"])

@router.get("/users", response_model=List[UserResponse])
async def list_all_users(
    email: Optional[str] = Query(None, description="Search by email query"),
    client_type: Optional[str] = Query(None),
    kyc_status: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    query = select(User)
    
    if email:
        query = query.where(User.email.ilike(f"%{email}%"))
    if client_type:
        query = query.where(User.client_type == client_type)
    if kyc_status:
        query = query.where(User.kyc_status == kyc_status)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
        
    query = query.order_by(User.created_at.desc()).limit(limit).offset(offset)
    
    result = await db.execute(query)
    users = result.scalars().all()
    return users


@router.get("/users/{user_id}")
async def get_user_full_profile(
    user_id: UUID,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis)
):
    # Fetch user details
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Fetch user positions
    positions = await get_positions_with_metrics(db, redis_client, str(user_id))
    
    # Fetch transactions
    tx_result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.executed_at.desc())
        .limit(50)
    )
    transactions = tx_result.scalars().all()
    
    return {
        "user": UserResponse.model_validate(user),
        "positions": positions,
        "transactions": transactions
    }


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user_status(
    user_id: UUID,
    kyc_status: Optional[str] = Query(None, description="pending | approved | rejected"),
    is_active: Optional[bool] = Query(None),
    role: Optional[str] = Query(None, description="user | admin"),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if kyc_status:
        if kyc_status not in ["pending", "approved", "rejected"]:
            raise HTTPException(status_code=400, detail="Invalid KYC status value")
        user.kyc_status = kyc_status
        
    if is_active is not None:
        user.is_active = is_active
        
    if role:
        if role not in ["user", "admin"]:
            raise HTTPException(status_code=400, detail="Invalid role value")
        user.role = role
        
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/contacts", response_model=List[ContactRequestResponse])
async def list_contact_requests(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ContactRequest)
        .order_by(ContactRequest.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    requests = result.scalars().all()
    return requests


@router.get("/stats")
async def get_system_wide_statistics(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis)
):
    # Total users count
    total_users_res = await db.execute(select(func.count(User.id)))
    total_users = total_users_res.scalar() or 0
    
    # Active users
    active_users_res = await db.execute(select(func.count(User.id)).where(User.is_active == True))
    active_users = active_users_res.scalar() or 0
    
    # Total transactions
    total_tx_res = await db.execute(select(func.count(Transaction.id)))
    total_tx = total_tx_res.scalar() or 0
    
    # New users registered today
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    new_users_res = await db.execute(select(func.count(User.id)).where(User.created_at >= today_start))
    new_users_today = new_users_res.scalar() or 0
    
    # Total Asset Under Management (AUM) - Sum of all portfolios value
    # We query all users IDs and calculate portfolio values
    user_ids_res = await db.execute(select(User.id).where(User.is_active == True))
    user_ids = user_ids_res.scalars().all()
    
    total_aum = float(0)
    for uid in user_ids:
        overview = await calculate_portfolio_overview(db, redis_client, str(uid))
        total_aum += float(overview["total_value"])
        
    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_aum": total_aum,
        "total_transactions": total_tx,
        "new_users_today": new_users_today
    }
