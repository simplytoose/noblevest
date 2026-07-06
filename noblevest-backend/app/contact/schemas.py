from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from uuid import UUID
from datetime import datetime

class ContactRequestCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    company: Optional[str] = Field(None, max_length=200)
    client_type: Optional[str] = Field(None, max_length=50)
    message: Optional[str] = Field(None, max_length=2000)

class ContactRequestResponse(ContactRequestCreate):
    id: UUID
    ip_address: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
