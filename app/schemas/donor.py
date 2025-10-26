from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime

class DonorBase(BaseModel):
    unique_donor_id: str
    name: str
    age: Optional[int] = None
    date_of_birth: Optional[date] = None
    gender: str
    is_priority: bool = False

class DonorCreate(DonorBase):
    pass

class DonorUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    is_priority: Optional[bool] = None

class DonorResponse(DonorBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class DonorPriorityUpdate(BaseModel):
    is_priority: bool
