from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.database import Base

class DonorFeedback(Base):
    __tablename__ = "donor_feedback"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    donor_id = Column(Integer, ForeignKey("donors.id", ondelete="CASCADE"), nullable=False, index=True)
    username = Column(String, nullable=False)
    feedback = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    donor = relationship("Donor", back_populates="feedbacks")

