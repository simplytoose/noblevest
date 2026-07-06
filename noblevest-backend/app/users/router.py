from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.database import get_db
from app.dependencies import get_current_user
from app.users.models import User, ActivityLog
from app.users.schemas import UserResponse, UserUpdate, PasswordUpdate
from app.auth.schemas import ActivityLogResponse
from app.auth.utils import hash_password, verify_password
from app.users.service import log_activity

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/me", response_model=UserResponse)
async def get_my_profile(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_my_profile(
    profile_in: UserUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    update_data = profile_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)

    await log_activity(
        db=db,
        user_id=current_user.id,
        action="update_profile",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata=update_data
    )

    return current_user


@router.patch("/me/password")
async def update_my_password(
    password_in: PasswordUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not verify_password(password_in.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect old password"
        )

    current_user.password_hash = hash_password(password_in.new_password)
    await db.commit()

    await log_activity(
        db=db,
        user_id=current_user.id,
        action="change_password",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )

    return {"detail": "Password successfully updated"}


@router.delete("/me", status_code=status.HTTP_200_OK)
async def delete_my_account(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Soft delete account
    current_user.is_active = False
    await db.commit()

    await log_activity(
        db=db,
        user_id=current_user.id,
        action="deactivate_account",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )

    return {"detail": "Account successfully deactivated"}


@router.get("/me/activity", response_model=List[ActivityLogResponse])
async def get_my_activity_log(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ActivityLog)
        .where(ActivityLog.user_id == current_user.id)
        .order_by(ActivityLog.created_at.desc())
        .limit(100)
    )
    logs = result.scalars().all()
    return logs
