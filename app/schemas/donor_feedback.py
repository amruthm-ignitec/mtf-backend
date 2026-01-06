from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class DonorFeedbackCreate(BaseModel):
    text: str

class DonorFeedbackResponse(BaseModel):
    id: int
    donor_id: int
    username: str
    feedback: str
    created_at: datetime
    
    class Config:
        from_attributes = True

