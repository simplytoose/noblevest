from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Literal
from uuid import UUID
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    client_type: str
    company: Optional[str] = None
    phone: Optional[str] = None

class UserResponse(UserBase):
    id: UUID
    is_verified: bool
    is_active: bool
    kyc_status: str
    role: str
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    company: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=30)
    client_type: Optional[Literal["trader", "hedge_fund", "family_office", "etf_issuer", "broker_dealer", "asset_manager"]] = None

class PasswordUpdate(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8, max_length=100)
