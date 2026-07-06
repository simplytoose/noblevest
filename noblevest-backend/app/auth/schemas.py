from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Literal
from uuid import UUID
from datetime import datetime

class UserRegister(BaseModel):
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=100)
    client_type: Literal["trader", "hedge_fund", "family_office", "etf_issuer", "broker_dealer", "asset_manager"] = "trader"
    company: Optional[str] = None
    phone: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: UUID

class ForgotPassword(BaseModel):
    email: EmailStr

class ResetPassword(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)

class ActivityLogResponse(BaseModel):
    id: UUID
    action: str
    ip_address: Optional[str]
    user_agent: Optional[str]
    metadata: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True
