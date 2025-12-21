from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import logging
from app.database.database import get_db
from app.models.user import User
from app.models.user_feedback import UserFeedback
from app.schemas.user_feedback import FeedbackCreate, FeedbackResponse
from app.api.v1.endpoints.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/", response_model=List[FeedbackResponse])
async def get_feedbacks(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all feedbacks. All authenticated users can see all feedbacks."""
    feedbacks = db.query(UserFeedback).order_by(UserFeedback.created_at.desc()).offset(skip).limit(limit).all()
    return feedbacks

@router.post("/", response_model=FeedbackResponse)
async def create_feedback(
    feedback: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new feedback. All authenticated users can submit feedback."""
    if not feedback.text or not feedback.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Feedback text cannot be empty"
        )
    
    # Create new feedback
    db_feedback = UserFeedback(
        username=current_user.full_name,
        feedback=feedback.text.strip()
    )
    
    db.add(db_feedback)
    db.commit()
    db.refresh(db_feedback)
    
    logger.info(f"Feedback created by user: {current_user.email} ({current_user.full_name})")
    return db_feedback

