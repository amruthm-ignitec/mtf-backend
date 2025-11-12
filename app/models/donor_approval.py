from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.database import Base
import enum

class ApprovalStatus(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"

class ApprovalType(str, enum.Enum):
    DOCUMENT = "document"
    DONOR_SUMMARY = "donor_summary"

class DonorApproval(Base):
    __tablename__ = "donor_approvals"
    
    id = Column(Integer, primary_key=True, index=True)
    donor_id = Column(Integer, ForeignKey("donors.id"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)  # Null if approving entire donor summary
    approval_type = Column(Enum(ApprovalType), nullable=False, default=ApprovalType.DONOR_SUMMARY)
    status = Column(Enum(ApprovalStatus), nullable=False, default=ApprovalStatus.PENDING)
    comment = Column(Text, nullable=False)  # Required comment explaining the decision
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    checklist_data = Column(Text, nullable=True)  # JSON string of checklist status at time of approval/rejection
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    donor = relationship("Donor", backref="approvals")
    document = relationship("Document", backref="approvals")
    approver = relationship("User", backref="approvals")


