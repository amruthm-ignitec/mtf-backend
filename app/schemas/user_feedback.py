from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class FeedbackCreate(BaseModel):
    text: str

class FeedbackResponse(BaseModel):
    id: int
    username: str
    feedback: str
    created_at: datetime
    
    class Config:
        from_attributes = True

