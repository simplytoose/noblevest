import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Cookie
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import redis.asyncio as redis
from loguru import logger

from app.database import get_db
from app.dependencies import get_redis, get_current_user
from app.config import settings
from app.users.models import User
from app.auth.schemas import UserRegister, UserLogin, Token, ForgotPassword, ResetPassword
from app.users.schemas import UserResponse
from app.auth.utils import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_refresh_token
)
from app.users.service import log_activity

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserRegister,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    # Check if exists
    result = await db.execute(select(User).where(User.email == user_in.email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The user with this email already exists."
        )

    # Hash password and create user
    hashed_pwd = hash_password(user_in.password)
    user = User(
        email=user_in.email,
        first_name=user_in.first_name,
        last_name=user_in.last_name,
        password_hash=hashed_pwd,
        client_type=user_in.client_type,
        company=user_in.company,
        phone=user_in.phone,
        is_verified=False,
        is_active=True,
        kyc_status="pending",
        role="user"
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    await log_activity(
        db=db,
        user_id=user.id,
        action="register",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"client_type": user_in.client_type}
    )

    # In a full flow, email confirmation token is sent here
    logger.info(f"User registered: {user.email}")
    return user


@router.post("/login", response_model=Token)
async def login(
    response: Response,
    request: Request,
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis)
):
    result = await db.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password"
        )
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    # Generate tokens
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    # Save refresh token in Redis (30 days TTL)
    await redis_client.setex(
        f"refresh_token:{user.id}:{refresh_token}",
        settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        "active"
    )

    # Update last login
    user.last_login = datetime.utcnow()
    await db.commit()

    await log_activity(
        db=db,
        user_id=user.id,
        action="login",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )

    # Set httpOnly cookie for refresh token
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )

    return Token(access_token=access_token, user_id=user.id)


@router.post("/refresh", response_model=Token)
async def refresh(
    response: Response,
    request: Request,
    refresh_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis)
):
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing"
        )

    user_id = decode_refresh_token(refresh_token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    # Check if token is blacklisted or not active
    token_status = await redis_client.get(f"refresh_token:{user_id}:{refresh_token}")
    if not token_status or token_status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is expired or revoked"
        )

    # Token rotation: invalidate old one
    await redis_client.delete(f"refresh_token:{user_id}:{refresh_token}")

    # Verify user
    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    # Generate new pair
    new_access_token = create_access_token(user.id)
    new_refresh_token = create_refresh_token(user.id)

    # Save new refresh token in Redis
    await redis_client.setex(
        f"refresh_token:{user.id}:{new_refresh_token}",
        settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        "active"
    )

    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )

    return Token(access_token=new_access_token, user_id=user.id)


@router.post("/logout")
async def logout(
    response: Response,
    request: Request,
    refresh_token: Optional[str] = Cookie(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis)
):
    if refresh_token:
        user_id = decode_refresh_token(refresh_token)
        if user_id and str(user_id) == str(current_user.id):
            # Delete/Blacklist the refresh token in Redis
            await redis_client.delete(f"refresh_token:{user_id}:{refresh_token}")
            # Explicitly blacklist
            await redis_client.setex(
                f"blacklist:{refresh_token}",
                settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
                "blacklisted"
            )

    response.delete_cookie(key="refresh_token")

    await log_activity(
        db=db,
        user_id=current_user.id,
        action="logout",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )

    return {"detail": "Successfully logged out"}


@router.post("/forgot-password")
async def forgot_password(
    form: ForgotPassword,
    redis_client: redis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.email == form.email))
    user = result.scalar_one_or_none()
    if not user:
        # Avoid user enumeration by returning OK
        return {"detail": "Password reset email sent if account exists"}

    # Generate one-time reset token
    reset_token = str(uuid.uuid4())
    # TTL: 1 hour
    await redis_client.setex(f"password_reset:{reset_token}", 3600, str(user.id))

    # Log/simulate sending the email
    logger.info(f"Password reset requested for {user.email}. Token: {reset_token}")
    
    # Simulate sending email containing link: /reset-password?token={reset_token}
    return {"detail": "Password reset email sent if account exists", "token": reset_token} # Returned for easier testing / client use


@router.post("/reset-password")
async def reset_password(
    form: ResetPassword,
    redis_client: redis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db)
):
    user_id = await redis_client.get(f"password_reset:{form.token}")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )

    # Invalidate token
    await redis_client.delete(f"password_reset:{form.token}")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    user.password_hash = hash_password(form.new_password)
    await db.commit()

    await log_activity(
        db=db,
        user_id=user.id,
        action="reset_password"
    )

    return {"detail": "Password successfully reset"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
